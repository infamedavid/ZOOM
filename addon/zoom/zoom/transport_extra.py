# transport_extra.py

import bpy
import math
import time
from . import state
from . import osc_feedback
from . import strips_extra
from . import strips_tools

# --- Función auxiliar de inhibición de transporte ---
def transporte_inhibido():
    """
    Devuelve False si no hay inhibición.
    Devuelve True si la navegación de strips inhibe todo.
    Devuelve un set de comandos a inhibir si el modo 'translate' está activo.
    """
    active_tools = state.control_state.get("active_tools", set())

    tools_that_inhibit = {"translate", "off_start", "off_end", "ripple", "ripple_move", "splice_trim", "slip", "push", "pull", "insert", "sleat", "slide", "camera","dolly", "truck", "pedestal", "pan", "tilt", "roll", "focal_length", "shift_x", "shift_y", "dof_distance", "fstop","dia_blades", "dia_rot", "dist_ratio","speed_tool", "multicam_tool","wipe_blur", "wipe_angle", "wipe_fader","cross_fader", "blur_x", "blur_y", "glow_threshold", "glow_clamp", "glow_boost", "glow_blur", "glow_quality","transf_pos_x", "transf_pos_y", "transf_scale_x", "transf_scale_y", "transf_rot", "transf_uniform_scale", "mark_translate"}

    if state.control_state.get("strip_nav_active", False):
        return True # La navegación de strips inhibe todo

    if tools_that_inhibit.intersection(active_tools):
        # Inhibe play, saltos, keyframes, marcadores y el 'hold' para avance rápido
        return {'play', 'jump', 'key', 'marker', 'hold'}

    return False

transport_hold_state = { "next": False, "prev": False, "timer": None, "delay": 0.5, "interval": 0.05, "start_time": 0.0 }

def strip_navigation_jog_update():
    if not state.control_state.get('jog_active', False) or not state.control_state.get('strip_nav_active', False):
        state.control_state['jog_timer'] = None
        return None
    strips_extra._navigate_preview_by_jog(state.control_state['jog_value'])
    return 0.05

def frame_hold_update():
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'hold' in inhibited):
        return None
    if not bpy.context.screen: return None
    direction = 1 if transport_hold_state.get("next") else -1 if transport_hold_state.get("prev") else 0
    if direction == 0:
        transport_hold_state["timer"] = None
        return None
    bpy.context.scene.frame_current += direction
    return transport_hold_state["interval"]

def handle_transport_hold(address, args):
    """
    Nuevo manejador para los comandos de mantener para avance/retroceso rápido.
    Reemplaza a transport_extra_receive.
    """
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'hold' in inhibited):
        return

    if not args or not isinstance(args[0], bool):
        return

    is_pressed = args[0]

    if is_pressed:
        direction = 'next' if address == "/hold_next" else 'prev'

        if direction == 'next':
            transport_hold_state.update({"start_time": time.time(), "next": True, "prev": False})
        else: # 'prev'
            transport_hold_state.update({"start_time": time.time(), "prev": True, "next": False})

        bpy.app.timers.register(start_hold_delay)

    else: # Botón liberado
        timer = transport_hold_state.get("timer")
        if timer and bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)

        transport_hold_state.update({"next": False, "prev": False, "timer": None})

def start_hold_delay():
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'hold' in inhibited):
        return None
    if transport_hold_state.get("next") or transport_hold_state.get("prev"):
        if time.time() - transport_hold_state.get("start_time", 0) >= transport_hold_state.get("delay", 0.5):
            if transport_hold_state.get("timer") is None:
                transport_hold_state["timer"] = bpy.app.timers.register(frame_hold_update, first_interval=0.01)
            return None
        return 0.01
    return None

class TRANSPORT_OT_CustomPlay(bpy.types.Operator):
    bl_idname = "transport.custom_play"
    bl_label = "Custom Play/Pause Operator"

    def execute(self, context):
        if not state.control_state.get('is_playing', False):
            if context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
        else:
            if not context.screen.is_animation_playing:
                reverse = state.control_state.get('play_direction') == 'bwd'
                bpy.ops.screen.animation_play(reverse=reverse)
        return {'FINISHED'}

class OSC_OT_MarkerNext(bpy.types.Operator):
    bl_idname = "osc_vse.marker_next"; bl_label = "Go to Next Marker"
    def execute(self, context):
        current = context.scene.frame_current; markers = sorted([m.frame for m in context.scene.timeline_markers if m.frame > current])
        if markers: context.scene.frame_current = markers[0]
        return {'FINISHED'}

class OSC_OT_MarkerPrev(bpy.types.Operator):
    bl_idname = "osc_vse.marker_prev"; bl_label = "Go to Previous Marker"
    def execute(self, context):
        current = context.scene.frame_current; markers = sorted([m.frame for m in context.scene.timeline_markers if m.frame < current], reverse=True)
        if markers: context.scene.frame_current = markers[0]
        return {'FINISHED'}

class OSC_OT_EnableCursorLock(bpy.types.Operator):
    bl_idname = "osc.enable_cursor_lock"; bl_label = "Enable/Disable Cursor Lock"
    state: bpy.props.BoolProperty(name="State", default=True)
    def execute(self, context):
        context.screen.use_follow = self.state; self.report({'INFO'}, f"🔒 Cursor lock {'ENABLED' if self.state else 'DISABLED'}")
        return {'FINISHED'}

class OSC_OT_FocusCursorFlash(bpy.types.Operator):
    bl_idname = "transport.focus_cursor_flash"; bl_label = "Focus Cursor Flash"; _timer = None
    def execute(self, context):
        context.screen.use_follow = True; bpy.ops.screen.animation_play()
        self.__class__._timer = bpy.app.timers.register(self.stop_flash, first_interval=0.05)
        return {'FINISHED'}
    @classmethod
    def stop_flash(cls):
        bpy.ops.screen.animation_cancel(restore_frame=True); bpy.context.screen.use_follow = False
        if cls._timer and bpy.app.timers.is_registered(cls._timer): bpy.app.timers.unregister(cls._timer)
        cls._timer = None
        return None

classes = (TRANSPORT_OT_CustomPlay, OSC_OT_MarkerNext, OSC_OT_MarkerPrev, OSC_OT_EnableCursorLock, OSC_OT_FocusCursorFlash)
def register():
    for cls in classes: bpy.utils.register_class(cls)
def unregister():
    for cls in reversed(classes): bpy.utils.unregister_class(cls)

# --- Manejadores de Lógica OSC ---
def handle_play_logic(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'play' in inhibited):
        return
    if not args or not isinstance(args[0], bool): return
    play_command = args[0]
    state.control_state['is_playing'] = play_command
    if play_command: state.control_state['play_direction'] = 'bwd' if state.control_state.get('shift_active') else 'fwd'
    if not state.control_state.get('jog_active'): bpy.ops.transport.custom_play('INVOKE_DEFAULT')

def handle_shift_logic(address, args):
    strips_extra.cancel_strip_time_timer()
    if args and isinstance(args[0], bool):
        state.control_state['shift_active'] = args[0]

def handle_jog_relative_toggle(address, args):
    if args and isinstance(args[0], bool):
        state.control_state['jog_relative_mode'] = args[0]
        print(f"Modo de Jog Relativo: {'ACTIVADO' if args[0] else 'DESACTIVADO'}.")

def handle_escape_logic(address, args):
    from . import strips_extra
    strips_extra.cancel_strip_time_timer()
    if bpy.context.screen.is_animation_playing:
        bpy.ops.screen.animation_cancel(restore_frame=True)
    if state.control_state.get('active_tools', set()):
        active_tools_to_clear = {"slip", "push", "pull"}
        if active_tools_to_clear.intersection(state.control_state.get('active_tools', set())):
             bpy.ops.ed.undo()
        state.control_state['active_tools'].clear()
        print("Active tools cleared and action reverted.")
    state.control_state['is_playing'] = False

def handle_timeline_jump(address, args):
    if not args or not isinstance(args[0], (int, float)): return
    slider_value = max(0.0, min(1.0, args[0]))
    scene = bpy.context.scene
    start_frame, end_frame = scene.frame_start, scene.frame_end
    duration = end_frame - start_frame
    if duration <= 0: return
    target_frame = start_frame + (duration * slider_value)
    scene.frame_current = round(target_frame)

def handle_timecode_feedback_toggle(address, args):
    if not args or not isinstance(args[0], bool): return
    should_run = args[0]
    state.control_state["timecode_feedback_active"] = should_run
    if should_run:
        state.control_state["timecode_last_send_time"] = 0.0
    print(f"Timecode feedback {'ACTIVADO' if should_run else 'DESACTIVADO'}.")

def handle_follow_toggle(address, args):
    if not args:
        print("handle_follow_toggle: no se recibió argumento booleano.")
        return
    val = args[0]
    if not isinstance(val, bool):
        try:
            val = bool(val)
        except Exception:
            print("handle_follow_toggle: argumento inválido:", args[0])
            return
    state.control_state['strip_nav_follow_active'] = val
    state.control_state['following_playhead'] = val
    print(f"Modo de seguimiento del 'viajero' {'ACTIVADO' if val else 'DESACTIVADO'}")
    if val:
        try:
            bpy.ops.transport.focus_cursor_flash('INVOKE_DEFAULT')
        except Exception:
            pass

# --- Nuevos handlers migrados desde simple_command_map ---
def handle_jump_start(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'jump' in inhibited):
        return
    bpy.ops.screen.frame_jump(end=False)

def handle_jump_end(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'jump' in inhibited):
        return
    bpy.ops.screen.frame_jump(end=True)

def handle_frame_next(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'hold' in inhibited):
        return

    active_tools = state.control_state.get('active_tools', set())
    if "translate" in active_tools:
        if args and args[0]:
            strips_tools.perform_translate_timeline(1)
        return
    if {"off_start", "off_end"}.intersection(active_tools):
        return

    if transporte_inhibido(): return
    bpy.ops.screen.frame_offset(delta=1)

def handle_frame_prev(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'hold' in inhibited):
        return

    active_tools = state.control_state.get('active_tools', set())
    if "translate" in active_tools:
        if args and args[0]:
            strips_tools.perform_translate_timeline(-1)
        return
    if {"off_start", "off_end"}.intersection(active_tools):
        return

    if transporte_inhibido(): return
    bpy.ops.screen.frame_offset(delta=-1)

def handle_key_next(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'key' in inhibited):
        return
    bpy.ops.screen.keyframe_jump(next=True)

def handle_key_prev(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'key' in inhibited):
        return
    bpy.ops.screen.keyframe_jump(next=False)

def handle_marker_next(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'marker' in inhibited):
        return
    bpy.ops.osc_vse.marker_next()

def handle_marker_prev(address, args):
    inhibited = transporte_inhibido()
    if inhibited is True or (isinstance(inhibited, set) and 'marker' in inhibited):
        return
    bpy.ops.osc_vse.marker_prev()

def handle_cursor_lock(address, args):
    if transporte_inhibido(): return
    state_val = True
    if args and isinstance(args[0], bool):
        state_val = args[0]
    bpy.ops.osc.enable_cursor_lock(state=state_val)

def handle_toggle_audio(address, args):
    """
    Alterna el audio global de la escena (bpy.context.scene.use_audio)
    y envía un mensaje de feedback con el nuevo estado.
    """
    if not args or not args[0]:
        return

    scene = bpy.context.scene

    scene.use_audio = not scene.use_audio
    new_state = scene.use_audio

    print(f"OSC VSE: Audio {'ACTIVADO' if new_state else 'DESACTIVADO'}")

    osc_feedback.send("/audio/state", 1 if new_state else 0)

def handle_toggle_audio_scrub(address, args):
    """
    Establece el estado del 'audio scrubbing' (bpy.context.scene.use_audio_scrub)
    basado en el valor booleano recibido (True/False).
    """
    if not args:
        return

    try:
        new_state = bool(args[0])
    except (ValueError, TypeError):
        return

    scene = bpy.context.scene
    scene.use_audio_scrub = new_state

    print(f"OSC VSE: Audio Scrubbing {'ACTIVADO' if new_state else 'DESACTIVADO'}")
    osc_feedback.send("/audio_scrub/state", 1 if new_state else 0)

def register_actions():
    pass