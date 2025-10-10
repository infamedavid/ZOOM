# control.py

import bpy
import math
from . import state
from . import osc_feedback
from . import strips_tools
from . import strips_advance
from . import offsets_tools
from . import transport_extra
from . import strips_extra
from . import config
from . import tools_extra

def jog_scrub_update():
    """
    Timer-driven scrub update para el jog.
    En lugar de mover scene.frame_current directamente (lo cual no activa
    el motor de audio), este handler realiza desplazamientos mediante
    bpy.ops.screen.frame_offset(...) para asegurar que Blender active
    la reproducción de audio en modo scrub.
    Mantiene la lógica previa de acumulador, curvas, modos relativos y shift.
    """
    if not state.control_state.get('jog_active', False):
        state.control_state['jog_timer'] = None
        return None

    scene = bpy.context.scene
    osc_props = scene.osc_vse_properties
    jog_input = state.control_state.get('jog_value', 0.0)
    abs_input = abs(jog_input)
    speed_multiplier = 0.0

    if abs_input > 0.0:
        if state.control_state.get('shift_active', False):
            # En shift limitamos el máximo a 1x (framerate actual) por diseño
            max_speed = 1.0
            min_speed = 1.0 / osc_props.min_scrub_speed if getattr(osc_props, "min_scrub_speed", 0) > 0 else 0.1
            if min_speed >= max_speed:
                min_speed = max_speed / 2.0
            speed_multiplier = min_speed + (max_speed - min_speed) * abs_input
        elif state.control_state.get('jog_relative_mode', False):
            min_speed = getattr(osc_props, "min_scrub_speed", 0.1)
            timeline_duration = float(scene.frame_end - scene.frame_start)
            relative_divisor = getattr(osc_props, "jog_relative_speed_divisor", 100.0)
            speed_from_duration = timeline_duration / relative_divisor if relative_divisor > 0 else 0.0
            effective_max_speed = getattr(osc_props, "max_scrub_speed", 8.0) + speed_from_duration
            speed_multiplier = min_speed + (effective_max_speed - min_speed) * (abs_input ** 3)
        else:
            min_speed = getattr(osc_props, "min_scrub_speed", 0.1)
            max_speed = getattr(osc_props, "max_scrub_speed", 8.0)
            speed_multiplier = min_speed + (max_speed - min_speed) * (abs_input ** 3)

    # Calcula fps efectivo
    fps = scene.render.fps / scene.render.fps_base if getattr(scene.render, "fps_base", 0) != 0 else scene.render.fps
    timer_interval = 0.02

    # Delta de frames (float) a acumular
    final_delta = (speed_multiplier * fps) * timer_interval * math.copysign(1.0, jog_input)
    # Usa acumulador para manejar fracciones hasta sumar un frame entero
    state.control_state.setdefault('jog_frame_accumulator', 0.0)
    state.control_state['jog_frame_accumulator'] += final_delta
    frames_to_move = int(state.control_state['jog_frame_accumulator'])

    if frames_to_move != 0:
        # Sustraemos la parte entera que vamos a mover
        state.control_state['jog_frame_accumulator'] -= frames_to_move

        # --- OPTIMIZACIÓN APLICADA AQUÍ ---
        # En lugar de un bucle, hacemos una única llamada al operador con el
        # delta total. Esto es mucho más rápido y debería eliminar el stuttering.
        try:
            if transport_extra.transporte_inhibido():
                return timer_interval # Salimos si el transporte está inhibido

            # Llamada única y optimizada
            bpy.ops.screen.frame_offset(delta=frames_to_move)

        except Exception as e:
            # Fallback: si por alguna razón bpy.ops falla, aplicamos el movimiento directo
            # para no dejar la reproducción bloqueada.
            print("jog_scrub_update: error al usar frame_offset, fallback a frame_current:", e)
            scene.frame_current += frames_to_move

    return timer_interval

def generic_jog_value_update():
    if not state.control_state.get('jog_active', False):
        state.control_state['jog_timer'] = None
        return None

    active_tools = state.control_state.get('active_tools', set())
    raw_jog_value = state.control_state.get('jog_value', 0.0)

    # Lógica para herramientas de offset (un frame por interacción)
    offset_tools = {"slip", "push", "pull", "sleat"}
    if offset_tools.intersection(active_tools):
        state.control_state.setdefault('offset_tool_accumulator', 0.0)
        state.control_state['offset_tool_accumulator'] += raw_jog_value * 20 # Sensibilidad aumentada

        frames_to_move = int(state.control_state['offset_tool_accumulator'])
        if frames_to_move != 0:
            state.control_state['offset_tool_accumulator'] -= frames_to_move
            direction = 1 if frames_to_move > 0 else -1

            for _ in range(abs(frames_to_move)):
                for tool in active_tools:
                    if tool in offset_tools:
                        handler = state.jog_actions.get(tool)
                        if handler:
                            handler(direction)
        return 0.05

    # Lógica existente para otras herramientas
    osc_props = bpy.context.scene.osc_vse_properties
    intensity = getattr(osc_props, "jog_tool_intensity", 1.0)
    exponent = 1.0 / intensity if intensity != 0 else 1.0
    transformed_value = math.copysign(abs(raw_jog_value) ** exponent, raw_jog_value) if raw_jog_value != 0 else 0

    for tool in active_tools:
        handler = state.jog_actions.get(tool)
        if handler:
            try:
                handler(transformed_value)
            except Exception as e:
                print(f"Error en generic_jog_value_update handler {tool}: {e}")

    return 0.05

def handle_jog_logic(address, args):
    if not args or not isinstance(args[0], bool): return
    is_touched = args[0]
    if is_touched == state.control_state.get('jog_active'): return
    state.control_state['jog_active'] = is_touched
    if is_touched:
        strips_extra.cancel_strip_time_timer()
        bpy.ops.ed.undo_push(message="OSC Jog Action")
        if bpy.context.screen.is_animation_playing: bpy.ops.screen.animation_cancel(restore_frame=False)
        if state.control_state.get('jog_timer') is None:
            if state.control_state.get('strip_nav_active', False):
                state.control_state['last_nav_time'] = 0.0
                state.control_state['jog_timer'] = bpy.app.timers.register(transport_extra.strip_navigation_jog_update)
            elif state.control_state.get('active_tools', set()):
                state.control_state['last_nav_time'] = 0.0
                state.control_state['jog_timer'] = bpy.app.timers.register(generic_jog_value_update)
            else:
                state.control_state['jog_frame_accumulator'] = 0.0
                state.control_state['jog_timer'] = bpy.app.timers.register(jog_scrub_update)
    else:
        tools_extra.reset_all_snap_states()
        if state.control_state.get('jog_timer') and bpy.app.timers.is_registered(state.control_state['jog_timer']):
            bpy.app.timers.unregister(state.control_state['jog_timer'])
        state.control_state['jog_timer'] = None
        if state.control_state.get('is_playing'): bpy.ops.transport.custom_play('INVOKE_DEFAULT')

def handle_jog_value(address, args):
    """CORREGIDO: Se añade la cancelación del timer."""
    if args and isinstance(args[0], (int, float)):
        strips_extra.cancel_strip_time_timer()
        state.control_state['jog_value'] = max(-1.0, min(1.0, args[0]))

def handle_next_strip(address, args):
    active_tools = state.control_state.get('active_tools', set())
    direction = 1

    if 'translate' in active_tools:
        if args and args[0]:
            bpy.ops.ed.undo_push(message="OSC Translate Move Next")
            strips_tools.perform_translate_timeline(direction)
        return

    if 'insert' in active_tools:
        if args and args[0]:
            strips_advance._perform_insert_from_nudge(direction)
        return


    if 'splice_trim' in active_tools:
        if args and args[0]:
            strips_advance._perform_splice_trim_from_nudge(direction)
        return


    offset_tools_activas = {"slip", "push", "pull", "sleat", "slide", "camera","speed_tool","multicam_tool","wipe_blur", "wipe_angle", "wipe_fader","cross_fader", "blur_x", "blur_y", "glow_threshold", "glow_clamp", "glow_boost", "glow_blur", "glow_quality","transf_pos_x", "transf_pos_y", "transf_scale_x", "transf_scale_y", "transf_rot", "transf_uniform_scale","mark_translate"}
    if offset_tools_activas.intersection(active_tools):
        if args and args[0]:
            for tool in active_tools:
                handler = state.plus_minus_actions.get(tool)
                if handler:
                    handler(direction)
                    return

    if 'ripple_move' in active_tools:
        if args and args[0]:
            bpy.ops.ed.undo_push(message="OSC Nudge Ripple")
            strips_tools._nudge_ripple_move(direction)
        return

    if 'off_start' in active_tools:
        bpy.ops.ed.undo_push(message="OSC Nudge Offset Start")
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current += direction
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        strips_tools._nudge_offset(direction, 'frame_offset_start')
        return

    if 'off_end' in active_tools:
        bpy.ops.ed.undo_push(message="OSC Nudge Offset End")
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current += direction
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        strips_tools._nudge_offset(direction * -1, 'frame_offset_end')
        return

    strips_extra.cancel_strip_time_timer()
    if state.control_state.get('strip_nav_active', False):
        strips_extra._navigate_preview_horizontal(direction)

def handle_prev_strip(address, args):
    active_tools = state.control_state.get('active_tools', set())
    direction = -1

    if 'translate' in active_tools:
        if args and args[0]:
            bpy.ops.ed.undo_push(message="OSC Translate Move Prev")
            strips_tools.perform_translate_timeline(direction)
        return

    if 'insert' in active_tools:
        if args and args[0]:
            strips_advance._perform_insert_from_nudge(direction)
        return

    if 'splice_trim' in active_tools:
        if args and args[0]:
            strips_advance._perform_splice_trim_from_nudge(direction)
        return

    offset_tools_activas = {"slip", "push", "pull", "sleat", "slide", "camera","speed_tool","multicam_tool","wipe_blur", "wipe_angle", "wipe_fader","cross_fader", "blur_x", "blur_y", "glow_threshold", "glow_clamp", "glow_boost", "glow_blur", "glow_quality","transf_pos_x", "transf_pos_y", "transf_scale_x", "transf_scale_y", "transf_rot", "transf_uniform_scale","mark_translate"}
    if offset_tools_activas.intersection(active_tools):
        if args and args[0]:
            for tool in active_tools:
                handler = state.plus_minus_actions.get(tool)
                if handler:
                    handler(direction)
                    return

    if 'ripple_move' in active_tools:
        if args and args[0]:
            bpy.ops.ed.undo_push(message="OSC Nudge Ripple")
            strips_tools._nudge_ripple_move(direction)
        return

    if 'off_start' in active_tools:
        bpy.ops.ed.undo_push(message="OSC Nudge Offset Start")
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current += direction
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        strips_tools._nudge_offset(direction, 'frame_offset_start')
        return

    if 'off_end' in active_tools:
        bpy.ops.ed.undo_push(message="OSC Nudge Offset End")
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current += direction
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
        strips_tools._nudge_offset(direction * -1, 'frame_offset_end')
        return

    strips_extra.cancel_strip_time_timer()
    if state.control_state.get('strip_nav_active', False):
        strips_extra._navigate_preview_horizontal(direction)

def handle_selection_plus_minus(address, args):
    if not args or not isinstance(args[0], bool) or not args[0]: return
    strips_extra.cancel_strip_time_timer()
    direction = 1 if address == "/plus" else -1
    if state.control_state.get('strip_nav_active', False):
        strips_extra._navigate_preview_vertical(direction)
    elif state.control_state.get('active_tools', set()):
        active_tools = state.control_state['active_tools']
        for tool in active_tools:
            handler = state.plus_minus_actions.get(tool)
            if handler: handler(direction)
    else:
        strips_extra._handle_zoom_step(-direction)