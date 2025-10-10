# offsets_tools.py
import bpy
from . import state
from . import osc_feedback # <-- AÑADIDO

# --- Funciones Auxiliares ---

def _get_visible_range(strip):
    """
    Devuelve el rango visible (start, end) de un strip, que es la forma
    correcta de determinar su posición en el timeline.
    """
    if hasattr(strip, "frame_final_start") and hasattr(strip, "frame_final_end"):
        return int(strip.frame_final_start), int(strip.frame_final_end)
    else:
        # Fallback para strips que no tengan estos atributos
        start = int(strip.frame_start + getattr(strip, "frame_offset_start", 0))
        end = int(start + strip.frame_final_duration)
        return start, end

def _find_completely_empty_channel(sequencer):
    """
    Escanea el VSE y devuelve el número del primer canal que no contiene ningún strip.
    """
    if not sequencer:
        return 1
    used_channels = {s.channel for s in sequencer.sequences_all}
    channel = 1
    while True:
        if channel not in used_channels:
            return channel
        channel += 1

def _get_anchors_by_channel(selection):
    """
    Implementa la regla "Una Ancla por Canal". Usa _get_visible_range
    para determinar correctamente cuál es el strip más a la izquierda.
    """
    if not selection:
        return []

    strips_by_channel = {}
    for strip in selection:
        if strip.channel not in strips_by_channel:
            strips_by_channel[strip.channel] = []
        strips_by_channel[strip.channel].append(strip)

    anchors = []
    for channel, strips in strips_by_channel.items():
        # Usamos el inicio visible real para la comparación
        leftmost_strip = min(strips, key=lambda s: _get_visible_range(s)[0])
        anchors.append(leftmost_strip)

    return anchors

def _get_connected_chain(anchor_strip):
    """
    Detecta dinámicamente la cadena de strips conectados a la derecha de un ancla.
    Usa _get_visible_range para asegurar la detección correcta de la conexión.
    """
    chain = []
    if not anchor_strip: return chain
    last_strip_end = _get_visible_range(anchor_strip)[1]

    all_strips_in_channel = sorted(
        [s for s in bpy.context.scene.sequence_editor.sequences_all if s.channel == anchor_strip.channel],
        key=lambda s: _get_visible_range(s)[0]
    )

    for strip in all_strips_in_channel:
        strip_start, strip_end = _get_visible_range(strip)
        if strip_start == last_strip_end:
            chain.append(strip)
            last_strip_end = strip_end
        elif strip_start > last_strip_end:
            break

    return chain

def _optimized_redraw():
    """
    En lugar de un update forzado del depsgraph, solo marca las áreas del
    VSE para que se redibujen. Es mucho más rápido.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()

# --- Lógica de las Herramientas ---

def _perform_slip_edit(delta):
    """
    Lógica principal de Slip, con la "danza de tres pasos" correcta y usando contexto.
    """
    delta = int(round(delta))
    slip_context = state.control_state.get('slip_context')
    if not slip_context:
        return

    moved_strip_names = slip_context.get("moved_strips", {}).keys()
    if not moved_strip_names:
        return

    sequencer = bpy.context.scene.sequence_editor
    if not sequencer:
        return

    strips_to_slip = [sequencer.sequences_all.get(name) for name in moved_strip_names]

    for strip in strips_to_slip:
        if not strip:
            continue

        new_offset_start = strip.frame_offset_start + delta
        new_offset_end = strip.frame_offset_end - delta
        new_frame_start = strip.frame_start - delta

        if new_offset_start < 0 or new_offset_end < 0:
            continue
        if (new_offset_start + strip.frame_final_duration) > strip.frame_duration:
            continue

        strip.frame_offset_start = new_offset_start
        strip.frame_offset_end = new_offset_end
        strip.frame_start = new_frame_start

    _optimized_redraw()


def _perform_push_edit(delta):
    """
    Lógica principal de Push, usando contexto para ser robusta.
    """
    delta = int(round(delta))
    push_context = state.control_state.get('push_context')
    if not push_context: return

    sequencer = bpy.context.scene.sequence_editor
    if not sequencer: return

    anchors_by_channel = push_context.get('anchors_by_channel', {})

    for channel, data in anchors_by_channel.items():
        anchor = sequencer.sequences_all.get(data['anchor_name'])
        satellites = [sequencer.sequences_all.get(name) for name in data['satellite_names']]

        if not anchor: continue

        chain = _get_connected_chain(anchor)

        if delta > 0: # Alargamiento: mover cadena y satélites, luego alargar ancla
            sorted_satellites = sorted([s for s in satellites if s], key=lambda s: _get_visible_range(s)[0])
            for s in reversed(chain): s.frame_start += delta
            for s in reversed(sorted_satellites):
                if s and s not in chain: s.frame_start += delta
            anchor.frame_final_duration += delta

        elif delta < 0: # Acortamiento: acortar ancla, luego mover cadena y satélites
            if anchor.frame_final_duration + delta < 1: continue
            anchor.frame_final_duration += delta
            for s in chain: s.frame_start += delta
            for s in satellites:
                if s and s not in chain: s.frame_start += delta

        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current = _get_visible_range(anchor)[1]

    _optimized_redraw()

def _perform_pull_edit(delta):
    """
    Lógica de Pull restaurada a la versión funcional.
    """
    delta = int(round(delta))
    pull_context = state.control_state.get('pull_context')
    if not pull_context: return

    sequencer = bpy.context.scene.sequence_editor
    if not sequencer: return

    d = -delta

    anchors_by_channel = pull_context.get('anchors_by_channel', {})

    for channel, data in anchors_by_channel.items():
        anchor = sequencer.sequences_all.get(data['anchor_name'])
        satellites = [sequencer.sequences_all.get(name) for name in data['satellite_names']]
        if not anchor: continue

        new_offset_start = anchor.frame_offset_start + d
        if new_offset_start < 0 or (new_offset_start + anchor.frame_final_duration) > anchor.frame_duration:
            continue

        duration_change = -d
        chain = _get_connected_chain(anchor)

        if duration_change > 0:
            sorted_satellites = sorted([s for s in satellites if s], key=lambda s: _get_visible_range(s)[0])
            for s in reversed(chain): s.frame_start += duration_change
            for s in reversed(sorted_satellites):
                if s and s not in chain: s.frame_start += duration_change
            anchor.frame_offset_start += d
            anchor.frame_start -= d
        elif duration_change < 0:
            anchor.frame_offset_start += d
            anchor.frame_start -= d
            for s in chain: s.frame_start += duration_change
            for s in satellites:
                if s and s not in chain: s.frame_start += duration_change

        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current = _get_visible_range(anchor)[0]

    _optimized_redraw()

def _perform_sleat_edit(delta):
    """
    Lógica de Sleat: Roll Edit si están conectados, Cerrar Hueco si no.
    """
    delta = int(round(delta))
    context = state.control_state.get('sleat_context')
    if not context: return

    sequencer = bpy.context.scene.sequence_editor
    if not sequencer: return

    strip_A = sequencer.sequences_all.get(context.get('left_strip_name'))
    strip_B = sequencer.sequences_all.get(context.get('right_strip_name'))
    if not strip_A or not strip_B: return

    are_connected = _get_visible_range(strip_A)[1] == _get_visible_range(strip_B)[0]

    if are_connected:
        # --- MODO ROLL EDIT ---
        if delta > 0: # Mover corte a la derecha (alargar A, acortar B)
            if strip_B.frame_final_duration - delta < 1 or (strip_A.frame_final_duration + delta) > strip_A.frame_duration:
                return

            strip_B.frame_offset_start += delta
            strip_A.frame_final_duration += delta

        elif delta < 0: # Mover corte a la izquierda (acortar A, alargar B)
            if strip_A.frame_final_duration + delta < 1 or strip_B.frame_offset_start + delta < 0:
                return

            strip_A.frame_final_duration += delta
            strip_B.frame_offset_start += delta

    else:
        # --- MODO CERRAR HUECO ---
        if delta > 0: # Alargar A hacia la derecha
            if strip_A.frame_offset_end - delta < 0: return
            strip_A.frame_offset_end -= delta

        elif delta < 0: # Alargar B hacia la izquierda
            if strip_B.frame_offset_start + delta < 0: return
            strip_B.frame_offset_start += delta

    # --- Lógica de seguimiento del Playhead (unificada) ---
    if state.control_state.get('strip_nav_follow_active', False):
        if delta > 0:
            bpy.context.scene.frame_current = _get_visible_range(strip_A)[1]
        elif delta < 0:
            bpy.context.scene.frame_current = _get_visible_range(strip_B)[0]

    _optimized_redraw()


# --- Manejadores de Activación OSC ---

def _handle_generic_activation(tool_name, args, use_safe_channel=False, use_stateful_selection=False):
    if not args or not isinstance(args[0], bool): return
    is_pressed = args[0]
    sequencer = bpy.context.scene.sequence_editor

    if is_pressed:
        if not sequencer or not bpy.context.selected_sequences: return

        selection = list(bpy.context.selected_sequences)

        if tool_name == "sleat":
            if len(selection) != 2 or selection[0].channel != selection[1].channel:
                print("OSC Sleat Tool: Se deben seleccionar exactamente dos strips en el mismo canal.")
                return

        bpy.ops.ed.undo_push(message=f"OSC {tool_name.capitalize()} Edit")
        context_data = {}

        if tool_name == "sleat":
            strip_A = min(selection, key=lambda s: _get_visible_range(s)[0])
            strip_B = max(selection, key=lambda s: _get_visible_range(s)[0])
            context_data['left_strip_name'] = strip_A.name
            context_data['right_strip_name'] = strip_B.name
        else:
            anchors = _get_anchors_by_channel(selection)
            if not anchors: return

            if use_safe_channel:
                safe_channel = _find_completely_empty_channel(sequencer)
                context_data["moved_strips"] = {s.name: s.channel for s in anchors}
                for strip in anchors: strip.channel = safe_channel

            if use_stateful_selection:
                anchors_by_channel = {}
                for anchor in anchors:
                    satellite_names = [s.name for s in selection if s.channel == anchor.channel and s.name != anchor.name]
                    anchors_by_channel[anchor.channel] = {
                        'anchor_name': anchor.name,
                        'satellite_names': satellite_names
                    }
                context_data['anchors_by_channel'] = anchors_by_channel

        state.control_state[f'{tool_name}_context'] = context_data
        state.control_state['active_tools'].add(tool_name)

        osc_feedback.send_active_tool_feedback() # <-- MODIFICADO

        print(f"OSC {tool_name.capitalize()} Tool: ACTIVADA.")
    else:
        if tool_name in state.control_state.get('active_tools', set()):
            context_name = f'{tool_name}_context'
            if use_safe_channel:
                context = state.control_state.get(context_name, {})
                moved_info = context.get("moved_strips", {})
                if sequencer and moved_info:
                    for name, channel in moved_info.items():
                        strip = sequencer.sequences_all.get(name)
                        if strip: strip.channel = channel

            if context_name in state.control_state:
                del state.control_state[context_name]
            state.control_state['active_tools'].discard(tool_name)

            osc_feedback.send_active_tool_feedback() # <-- MODIFICADO

            print(f"OSC {tool_name.capitalize()} Tool: DESACTIVADA.")

def handle_slip_activation(address, args):
    _handle_generic_activation("slip", args, use_safe_channel=True)

def handle_push_activation(address, args):
    _handle_generic_activation("push", args, use_stateful_selection=True)

def handle_pull_activation(address, args):
    _handle_generic_activation("pull", args, use_stateful_selection=True)

def handle_sleat_activation(address, args):
    _handle_generic_activation("sleat", args)

# --- INICIO DE LA NUEVA HERRAMIENTA "SLIDE" ---

def _find_connected_neighbors(strip):
    """
    Encuentra los vecinos DIRECTAMENTE CONECTADOS a un strip en el mismo canal.
    """
    left_neighbor, right_neighbor = None, None
    main_start, main_end = _get_visible_range(strip)
    strips_in_channel = [s for s in bpy.context.scene.sequence_editor.sequences_all
                        if s.channel == strip.channel and s.name != strip.name]
    for neighbor in strips_in_channel:
        if _get_visible_range(neighbor)[1] == main_start:
            left_neighbor = neighbor
        elif _get_visible_range(neighbor)[0] == main_end:
            right_neighbor = neighbor
    return left_neighbor, right_neighbor

def _find_nearest_neighbors(strip):
    """
    Encuentra los vecinos más cercanos (conectados o no) a un strip.
    """
    nearest_left, nearest_right = None, None
    main_start, _ = _get_visible_range(strip)
    strips_in_channel = [s for s in bpy.context.scene.sequence_editor.sequences_all
                        if s.channel == strip.channel and s.name != strip.name]
    left_candidates = [s for s in strips_in_channel if _get_visible_range(s)[0] < main_start]
    right_candidates = [s for s in strips_in_channel if _get_visible_range(s)[0] > main_start]
    if left_candidates:
        nearest_left = max(left_candidates, key=lambda s: _get_visible_range(s)[0])
    if right_candidates:
        nearest_right = min(right_candidates, key=lambda s: _get_visible_range(s)[0])
    return nearest_left, nearest_right

def _update_slide_playhead(strip, delta):
    """
    Gestiona el Snap del Playhead (/fcur) durante la operación de Slide.
    """
    if not state.control_state.get('strip_nav_follow_active', False):
        return
    nearest_left, nearest_right = _find_nearest_neighbors(strip)
    target_frame = None
    if delta > 0 and nearest_right:
        target_frame = _get_visible_range(nearest_right)[0]
    elif delta < 0 and nearest_left:
        target_frame = _get_visible_range(nearest_left)[1]
    if target_frame is not None:
        bpy.context.scene.frame_current = target_frame

def _perform_slide_edit(delta):
    """
    Función principal de la herramienta Slide, implementada con la secuencia de
    operaciones acordada para evitar solapamientos.
    """
    delta = int(round(delta))
    if delta == 0: return

    context = state.control_state.get('slide_context')
    if not context: return

    sequencer = bpy.context.scene.sequence_editor
    strips_to_move = [sequencer.sequences_all.get(name) for name in context.get('strips_to_move', [])]

    # --- LÓGICA DE SNAP (BRINCOS) ---
    if state.control_state.get('snap_active', False) and not context.get('snap_jump_performed', False):
        context['snap_jump_performed'] = True
        jump_delta = 0

        # Se calcula el brinco basado en el primer strip de la selección
        if strips_to_move:
            strip = strips_to_move[0]
            left_conn, right_conn = _find_connected_neighbors(strip)
            nearest_left, nearest_right = _find_nearest_neighbors(strip)

            if delta > 0 and nearest_right and not right_conn:
                jump_delta = _get_visible_range(nearest_right)[0] - _get_visible_range(strip)[1]
            elif delta < 0 and nearest_left and not left_conn:
                jump_delta = _get_visible_range(nearest_left)[1] - _get_visible_range(strip)[0]

        if jump_delta != 0:
            delta = jump_delta

    # --- BUCLE DE MOVIMIENTO INDEPENDIENTE POR CANAL ---
    for strip in strips_to_move:
        if not strip: continue

        left_conn, right_conn = _find_connected_neighbors(strip)
        nearest_left, nearest_right = _find_nearest_neighbors(strip)

        # --- LÓGICA DE LÍMITES Y BLOQUEOS (POR CANAL) ---
        can_move = True
        if delta > 0: # Moviendo a la derecha (+)
            if right_conn and right_conn.frame_final_duration - delta < 1: can_move = False
            if left_conn and hasattr(left_conn, 'frame_offset_end') and left_conn.frame_offset_end - delta < 0: can_move = False
            if nearest_right and not right_conn and _get_visible_range(strip)[1] + delta > _get_visible_range(nearest_right)[0]:
                if nearest_right.frame_final_duration - delta < 1: can_move = False
        elif delta < 0: # Moviendo a la izquierda (-)
            if left_conn and left_conn.frame_final_duration + delta < 1: can_move = False
            if right_conn and hasattr(right_conn, 'frame_offset_start') and right_conn.frame_offset_start + delta < 0: can_move = False
            if nearest_left and not left_conn and _get_visible_range(strip)[0] + delta < _get_visible_range(nearest_left)[1]:
                 if nearest_left.frame_final_duration + delta < 1: can_move = False

        if not can_move:
            continue

        # --- APLICACIÓN DE LA LÓGICA DE EDICIÓN CON SECUENCIA SEGURA ---

        if delta > 0: # SECUENCIA: R -> M -> L
            # 1. Modificar R (si existe)
            if right_conn:
                right_conn.frame_offset_start += delta
            elif nearest_right and _get_visible_range(strip)[1] + delta > _get_visible_range(nearest_right)[0]:
                overlap = (_get_visible_range(strip)[1] + delta) - _get_visible_range(nearest_right)[0]
                nearest_right.frame_offset_start += overlap
                nearest_right.frame_final_duration -= overlap

            # 2. Mover M
            strip.frame_start += delta

            # 3. Modificar L (si existe)
            if left_conn:
                left_conn.frame_offset_end -= delta

        elif delta < 0: # SECUENCIA: L -> M -> R
            # 1. Modificar L (si existe)
            if left_conn:
                left_conn.frame_offset_end -= delta # delta es negativo, por lo que suma
            elif nearest_left and _get_visible_range(strip)[0] + delta < _get_visible_range(nearest_left)[1]:
                 overlap = _get_visible_range(nearest_left)[1] - (_get_visible_range(strip)[0] + delta)
                 nearest_left.frame_offset_end += overlap

            # 2. Mover M
            strip.frame_start += delta

            # 3. Modificar R (si existe)
            if right_conn:
                right_conn.frame_offset_start += delta

        # Actualizar Playhead si está activo
        _update_slide_playhead(strip, delta)

    _optimized_redraw()

def handle_slide_activation(address, args):
    """
    Manejador OSC para activar y desactivar la herramienta Slide.
    """
    if not args or not isinstance(args[0], bool): return
    is_pressed = args[0]
    tool_name = "slide"

    if is_pressed:
        selected_strips = bpy.context.selected_sequences
        if not selected_strips: return
        bpy.ops.ed.undo_push(message="OSC Slide Edit")

        context_data = {
            'strips_to_move': [s.name for s in selected_strips],
            'snap_jump_performed': False
        }
        state.control_state['slide_context'] = context_data
        state.control_state['active_tools'].add(tool_name)

        osc_feedback.send_active_tool_feedback() # <-- MODIFICADO

        print("OSC Slide Tool: ACTIVADA.")
    else:
        if tool_name in state.control_state.get('active_tools', set()):
            state.control_state['active_tools'].discard(tool_name)
            if 'slide_context' in state.control_state:
                del state.control_state['slide_context']

            osc_feedback.send_active_tool_feedback() # <-- MODIFICADO

            print("OSC Slide Tool: DESACTIVADA.")

# --- FIN DE LA NUEVA HERRAMIENTA "SLIDE" ---

def register_actions():
    state.jog_actions['slip'] = _perform_slip_edit
    state.jog_actions['push'] = _perform_push_edit
    state.jog_actions['pull'] = _perform_pull_edit
    state.jog_actions['sleat'] = _perform_sleat_edit
    # --- AÑADIDO PARA SLIDE ---
    state.jog_actions['slide'] = _perform_slide_edit
    state.plus_minus_actions['slide'] = _perform_slide_edit

def register():
    pass

def unregister():
    pass
