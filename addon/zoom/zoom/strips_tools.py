# strips_tools.py

import bpy
import time
from . import state
from . import adds
from . import groups_logic  # <-- IMPORTADO PARA AUTO MIRROR
from . import config

def handle_select_grouped_on_exit_toggle(address, args): # <-- RENOMBRADO
    if not args or not isinstance(args[0], bool): return
    new_state = args[0]
    state.control_state['select_grouped_on_exit'] = new_state # <-- RENOMBRADO
    print(f"Modo 'Select Grouped on Exit': {'ACTIVADO' if new_state else 'DESACTIVADO'}")

# --- Sistema de Grab/Translate ---
def _get_selected_strips_for_translate():
    return [s for s in bpy.context.scene.sequence_editor.sequences if s.select]

def _calculate_grab_speed_multiplier():
    scene = bpy.context.scene
    osc_props = scene.osc_vse_properties
    if state.control_state.get('shift_active', False):
        return osc_props.grab_user_speed
    project_duration = float(scene.frame_end - scene.frame_start)
    if project_duration <= 0 or config.GRAB_PROJECT_LENGTH_DIVISOR <= 0:
        project_factor = 1.0
    else:
        project_factor = 1.0 + (project_duration / config.GRAB_PROJECT_LENGTH_DIVISOR)
    return osc_props.grab_user_speed * project_factor

def perform_translate_timeline(frame_delta):
    strips = _get_selected_strips_for_translate()
    if not strips: return

    final_delta = int(round(frame_delta))
    if final_delta == 0: return

    for strip in strips:
        strip.frame_start += final_delta

    # <<< AUTO MIRROR HOOK: chequeo de strips modificados por translate/move >>>
    if state.control_state.get("auto_mirror", False) and strips:
        scene = bpy.context.scene
        try:
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass

            updated = []
            if scene and scene.sequence_editor:
                for s in strips:
                    u = scene.sequence_editor.sequences_all.get(s.name)
                    if u:
                        updated.append(u)

            if updated:
                try:
                    groups_logic.run_auto_mirror_check(updated)
                except Exception as e:
                    print(f"AUTO MIRROR: error en run_auto_mirror_check (translate): {e}")
        except Exception as e:
            print(f"AUTO MIRROR: fallo preparando datos (translate): {e}")

    if state.control_state.get('strip_nav_follow_active', False):
        bpy.context.scene.frame_current += final_delta

def _perform_translate_channel(channel_delta):
    strips = _get_selected_strips_for_translate()
    if not strips: return
    for strip in strips:
        new_channel = strip.channel + channel_delta
        strip.channel = max(1, new_channel)

# --- INICIO: NUEVO SNAP ---
def _ensure_snap_defaults():
    cs = state.control_state
    if 'snap_active' not in cs:
        cs['snap_active'] = False
    if 'snap_targets' not in cs:
        cs['snap_targets'] = {
            "startstrips": True, "endstrips": True, "audiostrips": True, "mutestrips": True,
            "marker": False, "keyframe": False, "playhead": False, "start": False, "end": False,
        }
    if 'snap_session' not in cs:
        cs['snap_session'] = {
            "active": False, "direction": 0, "candidates": [], "index": 0,
            "applied_delta": 0, "initial_positions": {}, "anchors": [],
            "last_jump_time": 0.0, "accumulator": 0.0,
        }
    if 'last_cut_right_registered' not in cs:
        cs['last_cut_right_registered'] = []  # <-- registro simple de nacidos RIGHT

def _collect_all_targets():
    print(">>> COLLECT SNAP TARGETS CALLED")
    _ensure_snap_defaults()
    cs = state.control_state
    targets = set()
    scene = bpy.context.scene
    if not (scene and scene.sequence_editor): return set()
    seqs_all = list(scene.sequence_editor.sequences_all)

    for s in seqs_all:
        if s.select: continue
        if getattr(s, "mute", False) and not cs['snap_targets'].get("mutestrips", False): continue
        if s.type == 'SOUND' and not cs['snap_targets'].get("audiostrips", False): continue
        if cs['snap_targets'].get("startstrips", False): targets.add(s.frame_final_start)
        if cs['snap_targets'].get("endstrips", False): targets.add(s.frame_final_end)

    if cs['snap_targets'].get("marker", False):
        for m in bpy.context.scene.timeline_markers: targets.add(m.frame)
    if cs['snap_targets'].get("keyframe", False):
        try:
            for action in bpy.data.actions:
                if not action: continue
                for fc in action.fcurves:
                    for kp in fc.keyframe_points: targets.add(int(round(kp.co.x)))
        except Exception: pass
    if cs['snap_targets'].get("playhead", False): targets.add(bpy.context.scene.frame_current)
    if cs['snap_targets'].get("start", False): targets.add(bpy.context.scene.frame_start)
    if cs['snap_targets'].get("end", False): targets.add(bpy.context.scene.frame_end)

    print(f">>> TARGETS FOUND ({len(targets)}): {sorted(list(targets))}")
    return targets

def _build_snap_candidates(direction):
    _ensure_snap_defaults()
    scene = bpy.context.scene
    selected = [s for s in scene.sequence_editor.sequences if s.select] if (scene and scene.sequence_editor) else []
    if not selected: return []

    anchors = [s.frame_final_start for s in selected] if direction < 0 else [s.frame_final_end for s in selected]
    targets = _collect_all_targets()
    if not targets: return []

    deltas = {t - a for a in anchors for t in targets if (direction < 0 and t - a < 0) or (direction > 0 and t - a > 0)}
    if not deltas: return []
    return sorted(list(deltas), reverse=direction < 0)

def _init_snap_session(direction):
    _ensure_snap_defaults()
    cs = state.control_state
    ss = cs['snap_session']
    ss.update({
        "active": True, "direction": direction, "candidates": _build_snap_candidates(direction),
        "index": 0, "applied_delta": 0, "accumulator": 0.0, "last_jump_time": time.time()
    })
    print(f">>> SNAP SESSION INITIALIZED. Direction: {direction}. Candidates: {ss['candidates']}")
    selected = [s for s in bpy.context.scene.sequence_editor.sequences if s.select]
    ss['initial_positions'] = {s.name: s.frame_start for s in selected}
    ss['anchors'] = [s.frame_final_start for s in selected] if direction < 0 else [s.frame_final_end for s in selected]

def _clear_snap_session():
    _ensure_snap_defaults()
    state.control_state['snap_session'].update({
        "active": False, "direction": 0, "candidates": [], "index": 0, "applied_delta": 0,
        "initial_positions": {}, "anchors": [], "accumulator": 0.0, "last_jump_time": 0.0
    })

def _apply_snap_index(index):
    print(f">>> APPLY SNAP CALLED for index: {index}")
    _ensure_snap_defaults()
    ss = state.control_state['snap_session']
    if not ss['active'] or not (0 <= index < len(ss['candidates'])):
        print(">>> APPLY SNAP CANCELED: Session not active or index out of bounds.")
        return

    desired_total = ss['candidates'][index]
    incremental = desired_total - ss['applied_delta']
    print(f">>> CLOSEST TARGET (delta total): {desired_total}, Delta incremental a aplicar: {incremental}")
    if incremental == 0: return

    perform_translate_timeline(incremental)
    ss['applied_delta'] = desired_total
    ss['index'] = index
    ss['last_jump_time'] = time.time()

def _maybe_step_snap(direction, jog_value):
    _ensure_snap_defaults()
    ss = state.control_state['snap_session']
    if not ss['active'] or not ss['candidates']: return False

    ss['accumulator'] += abs(jog_value)
    threshold = 1.0

    if ss['accumulator'] >= threshold:
        steps = int(ss['accumulator'] // threshold)
        ss['accumulator'] -= steps * threshold
        new_index = min(ss['index'] + steps, len(ss['candidates']) - 1)
        if new_index != ss['index']:
            _apply_snap_index(new_index)
            return True
    return False

def _perform_translate_from_jog(jog_value):
    _ensure_snap_defaults()
    cs = state.control_state
    speed_multiplier = _calculate_grab_speed_multiplier()

    print(">>> SNAP STATE:", cs.get("snap_active"))
    print(">>> SNAP TARGETS:", cs.get("snap_targets"))

    if not cs.get('snap_active', False) or 'translate' not in cs.get('active_tools', set()):
        frame_delta = jog_value * config.GRAB_BASE_SENSITIVITY * speed_multiplier
        print(f">>> perform_translate_timeline (normal mode) called with delta: {frame_delta}")
        perform_translate_timeline(frame_delta)
        return

    if jog_value == 0.0: return
    direction = -1 if jog_value < 0 else 1

    ss = cs['snap_session']
    if not ss['active'] or ss['direction'] != direction:
        _clear_snap_session()
        _init_snap_session(direction)

    if not ss['candidates']:
        perform_translate_timeline(jog_value * config.GRAB_BASE_SENSITIVITY * speed_multiplier)
        return

    if ss['applied_delta'] == 0:
        _apply_snap_index(0)
        return

    if _maybe_step_snap(direction, jog_value):
        return

def handle_translate_activation(address, args):
    if not args or not isinstance(args[0], bool): return
    is_pressed = args[0]
    tool_name = "translate"

    if is_pressed:
        print("\n--- GRAB TOOL ACTIVATED ---")
        if not bpy.context.selected_sequences: return

        bpy.ops.ed.undo_push(message="OSC Tool: Grab")

        _ensure_snap_defaults()
        _clear_snap_session()
        if tool_name not in state.control_state['active_tools']:
            state.control_state['active_tools'].add(tool_name)
            osc_feedback.send_active_tool_feedback() # <-- feedback
    else:
        print("--- GRAB TOOL DEACTIVATED ---\n")
        if tool_name in state.control_state['active_tools']:
            state.control_state['active_tools'].discard(tool_name)
            osc_feedback.send_active_tool_feedback() # <-- MODIFICADO

        moved_strips = list(bpy.context.selected_sequences)

        state.control_state['tool_temp_linked_selection'].clear()
        _clear_snap_session()

        # <<< AUTO MIRROR HOOK: chequeo final al soltar GRAB >>>
        if state.control_state.get("auto_mirror", False) and moved_strips:
            scene = bpy.context.scene
            try:
                try:
                    bpy.context.view_layer.update()
                except Exception:
                    pass

                names = [s.name for s in moved_strips]
                updated = []
                if scene and scene.sequence_editor:
                    for n in names:
                        u = scene.sequence_editor.sequences_all.get(n)
                        if u:
                            updated.append(u)
                if updated:
                    try:
                        groups_logic.run_auto_mirror_check(updated)
                    except Exception as e:
                        print(f"AUTO MIRROR: error en run_auto_mirror_check (grab release): {e}")
            except Exception as e:
                print(f"AUTO MIRROR: fallo preparando datos (grab release): {e}")

def _enable_sync_visible_range():
    for area in bpy.context.screen.areas:
        if area.type in {'DOPESHEET_EDITOR', 'TIMELINE', 'SEQUENCE_EDITOR'}:
            if hasattr(area.spaces.active, 'show_locked_time'):
                area.spaces.active.show_locked_time = True

def _focus_on_selected_strips(clear_preview_after=True):
    scene = bpy.context.scene
    sequencer = scene.sequence_editor
    if not (sequencer and bpy.context.selected_sequences): return

    dopesheet_area = next((area for area in bpy.context.screen.areas if area.type == 'DOPESHEET_EDITOR'), None)
    if not dopesheet_area: return

    bpy.ops.sequencer.set_range_to_strips(preview=True)
    try:
        with bpy.context.temp_override(window=bpy.context.window, area=dopesheet_area, region=dopesheet_area.regions[-1]):
            bpy.ops.anim.scene_range_frame()
            if clear_preview_after: bpy.ops.anim.previewrange_clear()
    except Exception as e:
        if clear_preview_after and scene.use_preview_range:
            with bpy.context.temp_override(window=bpy.context.window, area=dopesheet_area, region=dopesheet_area.regions[-1]):
                bpy.ops.anim.previewrange_clear()

def handle_frame_clear(address, args):
    if not args or not args[0]: return
    _enable_sync_visible_range()
    from . import strips_extra
    strips_extra._reset_zoom_to_selection()

def handle_set_preview_range(address, args):
    if not bpy.context.selected_sequences: return
    _enable_sync_visible_range()
    _focus_on_selected_strips(clear_preview_after=False)

def handle_delete_preview_range(address, args):
    scene = bpy.context.scene
    if not scene.use_preview_range: return
    valid_area = next((area for area in bpy.context.screen.areas if area.type in {'DOPESHEET_EDITOR', 'SEQUENCE_EDITOR', 'TIMELINE'}), None)
    if not valid_area: return
    try:
        with bpy.context.temp_override(window=bpy.context.window, area=valid_area, region=valid_area.regions[-1]):
            bpy.ops.anim.previewrange_clear()
    except Exception: pass

def _perform_strip_offset(frame_delta, property_name):
    selected_strips = bpy.context.selected_sequences
    if not selected_strips or frame_delta == 0: return
    for strip in selected_strips:
        if hasattr(strip, property_name):
            setattr(strip, property_name, getattr(strip, property_name) + frame_delta)

    # <<< AUTO MIRROR HOOK: chequeo de strips modificados por cambio de offset >>>
    if state.control_state.get("auto_mirror", False):
        scene = bpy.context.scene
        try:
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass

            updated = []
            if scene and scene.sequence_editor:
                for s in selected_strips:
                    u = scene.sequence_editor.sequences_all.get(s.name)
                    if u:
                        updated.append(u)

            if updated:
                try:
                    groups_logic.run_auto_mirror_check(updated)
                except Exception as e:
                    print(f"AUTO MIRROR: error en run_auto_mirror_check (offset): {e}")
        except Exception as e:
            print(f"AUTO MIRROR: fallo preparando datos (offset): {e}")

def _perform_offset_from_jog(jog_value, property_name):
    osc_props = bpy.context.scene.osc_vse_properties
    speed_multiplier = osc_props.grab_user_speed
    if state.control_state.get('shift_active', False):
        speed_multiplier /= config.OFFSET_PRECISION_DIVISOR
    frame_delta = jog_value * config.OFFSET_JOG_SENSITIVITY * speed_multiplier
    state.control_state['offset_frame_accumulator'] += frame_delta
    frames_to_move = int(state.control_state['offset_frame_accumulator'])

    if frames_to_move != 0:
        state.control_state['offset_frame_accumulator'] -= frames_to_move
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current += frames_to_move
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        strip_delta = frames_to_move * -1 if property_name == 'frame_offset_end' else frames_to_move
        _perform_strip_offset(strip_delta, property_name)

def _nudge_offset(direction, property_name):
    _perform_strip_offset(direction, property_name)

def _nudge_ripple_move(direction):
    perform_translate_timeline(direction)

def handle_knife_activation(address, args):
    if not args or not isinstance(args[0], bool): return
    is_pressed, tool_name = args[0], "ripple_move"

    if is_pressed:
        cut_type = 'HARD' if address == '/knife_h' else 'SOFT'

        # <-- INICIO: MODIFICACIÓN PARA FEEDBACK ESPECIAL -->
        # Guardamos el nombre personalizado que queremos mostrar en la superficie
        custom_name = "KNIFE HRD" if cut_type == 'HARD' else "KNIFE SFT"
        state.control_state['active_tool_custom_name'] = custom_name
        # <-- FIN: MODIFICACIÓN PARA FEEDBACK ESPECIAL -->

        strips_to_cut = list(bpy.context.selected_sequences)
        if not strips_to_cut:
            # Limpiamos el nombre custom si la acción no procede
            state.control_state['active_tool_custom_name'] = None
            return print(f"OSC Ripple ({cut_type}): No hay strips seleccionados para cortar.")

        # ... (el resto de la lógica de corte no necesita cambios)
        override_context = adds.get_sequencer_context()
        if not override_context:
            state.control_state['active_tool_custom_name'] = None
            return print(f"OSC Ripple ({cut_type}) Error: No se encontró un área de 'Video Sequence Editor' visible.")

        cut_frame = bpy.context.scene.frame_current
        names_before_cut = {s.name for s in bpy.context.scene.sequence_editor.sequences_all}
        bpy.ops.ed.undo_push(message=f"OSC Ripple Cut ({cut_type})")

        new_strips = []
        try:
            with bpy.context.temp_override(**override_context):
                bpy.ops.sequencer.select_all(action='DESELECT')
                for strip in strips_to_cut:
                    strip.select = True
                if any(cut_frame > s.frame_final_start and cut_frame < s.frame_final_end for s in strips_to_cut):
                    bpy.ops.sequencer.split(frame=cut_frame, type=cut_type, side='RIGHT')

            # ... (continúa la lógica de identificación de nuevos strips...)
            all_strips_after_cut = bpy.context.scene.sequence_editor.sequences_all
            new_strips = [s for s in all_strips_after_cut if s.name not in names_before_cut]

            if not new_strips:
                state.control_state['active_tool_custom_name'] = None
                print("OSC Ripple: El corte no produjo nuevos strips.")
                return

            # ... (selección de nuevos strips y activación de la herramienta...)
            if tool_name not in state.control_state['active_tools']:
                state.control_state['active_tools'].add(tool_name)
                # La llamada a feedback ahora usará el nombre custom que guardamos
                osc_feedback.send_active_tool_feedback()
                print(f"OSC Ripple: Estado '{tool_name}' ({custom_name}) ACTIVADO.")

            # ... (resto de la lógica)

        except Exception as e:
            state.control_state['active_tool_custom_name'] = None # Limpiar en caso de error
            print(f"OSC Ripple ({cut_type}) Error: No se pudo ejecutar el corte. {e}")
        finally:
            if new_strips:
                groups_logic.register_specific_strips(new_strips)
    else: # al soltar el botón
        # Limpiamos todo al desactivar
        state.control_state['active_tool_custom_name'] = None
        if tool_name in state.control_state['active_tools']:
            state.control_state['active_tools'].discard(tool_name)
            osc_feedback.send_active_tool_feedback()
            print(f"OSC Ripple: Estado '{tool_name}' DESACTIVADO.")

def handle_snap_toggle(address, args):
    if not args or not isinstance(args[0], bool): return
    _ensure_snap_defaults()
    state.control_state["snap_active"] = args[0]
    print(f"OSC Snap: {'ACTIVADO' if args[0] else 'DESACTIVADO'}")
    if not args[0]: _clear_snap_session()

def handle_snap_target_toggle(address, args):
    if not args or not isinstance(args[0], bool): return
    _ensure_snap_defaults()
    mapping = {
        "/snap_startstrips": "startstrips", "/snap_endstrips": "endstrips",
        "/snap_audiostrips": "audiostrips", "/snap_mutestrips": "mutestrips",
        "/snap_marker": "marker", "/snap_keyframe": "keyframe",
        "/snap_playhead": "playhead", "/snap_start": "start", "/snap_end": "end",
    }
    key = mapping.get(address)
    if key:
        state.control_state['snap_targets'][key] = args[0]
        print(f"OSC Snap Target '{key}': {'ACTIVADO' if args[0] else 'DESACTIVADO'}")

def register(): pass
def unregister(): pass

def register_actions():
    state.jog_actions['translate'] = _perform_translate_from_jog
    state.plus_minus_actions['translate'] = lambda d: _perform_translate_channel(d)
    state.jog_actions['off_start'] = lambda v: _perform_offset_from_jog(v, 'frame_offset_start')
    state.jog_actions['off_end'] = lambda v: _perform_offset_from_jog(v, 'frame_offset_end')
    state.jog_actions['ripple_move'] = _perform_translate_from_jog
    state.plus_minus_actions['ripple_move'] = lambda d: _perform_translate_channel(d)