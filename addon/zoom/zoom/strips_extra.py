# strips_extra.py

import bpy
import math
import time
from bpy.app.handlers import persistent
from . import state
from . import osc_feedback
from . import strips_tools
from . import groups_logic
from . import offsets_tools
from . import strips_advance

# ---Feedback Visual y Grupos ---

GROUP_COLOR_PALETTE = ['COLOR_01', 'COLOR_04', 'COLOR_05', 'COLOR_06', 'COLOR_07', 'COLOR_08']
NEW_GROUP_COLOR = 'COLOR_02'

def _clear_all_group_colors():
    if not bpy.context.scene.sequence_editor: return
    seqs = bpy.context.scene.sequence_editor.sequences_all

    all_grouped_strips = set()
    for members in groups_logic.GROUPS.values():
        all_grouped_strips.update(members)

    for strip_name in all_grouped_strips:
        strip = seqs.get(strip_name)
        if strip and strip.color_tag != 'COLOR_03': # No limpiar el tag del viajero
            strip.color_tag = 'NONE'

def _apply_group_colors(specific_groups=None):
    if not bpy.context.scene.sequence_editor: return
    seqs = bpy.context.scene.sequence_editor.sequences_all

    sorted_groups = []
    for group_id, members in groups_logic.GROUPS.items():
        min_frame = float('inf')
        valid_group = False
        for name in members:
            strip = seqs.get(name)
            if strip:
                min_frame = min(min_frame, strip.frame_final_start)
                valid_group = True
        if valid_group:
            sorted_groups.append((min_frame, group_id))

    sorted_groups.sort()

    color_index = 0
    for _, group_id in sorted_groups:
        if specific_groups and group_id not in specific_groups:
            continue

        color = GROUP_COLOR_PALETTE[color_index % len(GROUP_COLOR_PALETTE)]
        for member_name in groups_logic.GROUPS[group_id]:
            strip = seqs.get(member_name)
            if strip:
                strip.color_tag = color
        color_index += 1

def handle_display_groups(address, args):
    if not args: return
    is_pressed = args[0]

    state.control_state['display_groups_active'] = is_pressed
    if is_pressed:
        _apply_group_colors()
    else:
        _clear_all_group_colors()



def handle_set_group(address, args):
    if not args or not args[0]: return
    if not state.control_state.get('strip_nav_active', False):
        print("OSC Grouping: Set Group solo está activo en el modo de navegación (Vstrip).")
        return

    working_set = set(bpy.context.selected_sequences)
    traveler_name = state.control_state.get("preview_strip_name")
    if traveler_name:
        traveler_strip = bpy.context.scene.sequence_editor.sequences_all.get(traveler_name)
        if traveler_strip:
            working_set.add(traveler_strip)

    new_group_info = groups_logic.set_group_from_selection(list(working_set))

    if new_group_info:

        # Enviar feedback de evento momentáneo para confirmar la creación del grupo.
        osc_feedback.send_action_feedback("GROUPED")


        new_member_names = set(new_group_info['members'])
        for strip in bpy.context.scene.sequence_editor.sequences_all:
            strip.select = strip.name in new_member_names

        state.control_state["selection_set"] = new_member_names

        # Feedback Visual
        if state.control_state.get('display_groups_active', False):
            _apply_group_colors()
        else:
            _clear_all_group_colors()
            seqs = bpy.context.scene.sequence_editor.sequences_all
            for member_name in new_member_names:
                strip = seqs.get(member_name)
                if strip:
                    strip.color_tag = NEW_GROUP_COLOR

def handle_ungroup(address, args):
    if not args or not args[0]: return
    if not state.control_state.get('strip_nav_active', False):
        print("OSC Grouping: Ungroup solo está activo en el modo de navegación (Vstrip).")
        return

    _clear_all_group_colors()
    groups_logic.ungroup_from_selection(bpy.context.selected_sequences)
    if state.control_state.get('display_groups_active', False):
        _apply_group_colors()

def handle_select_grouped(address, args):
    if not args or not args[0]: return
    groups_logic.expand_selection_to_groups()

# ---Selección del último grupo creado ---

def handle_select_last_grouped(address, args):
    """
    Toggle para la bandera auto_select_last_grouped.
    Se espera args[0] booleano (True/False).
    """
    if not args or not isinstance(args[0], bool): return
    new_state = args[0]
    state.control_state['auto_select_last_grouped'] = new_state
    print(f"OSC Grouping: auto_select_last_grouped -> {'ACTIVADO' if new_state else 'DESACTIVADO'}")

def handle_select_last_grouped_trigger(address, args):
    """
    Trigger para seleccionar manualmente el último grupo creado.
    No requiere args; si hay last_group_id en state lo selecciona.
    """
    last_gid = state.control_state.get('last_group_id')
    if not last_gid:
        print("OSC Grouping: No hay último grupo registrado para seleccionar.")
        return

    members = groups_logic.GROUPS.get(last_gid)
    if not members:
        print(f"OSC Grouping: El grupo '{last_gid}' no existe o no tiene miembros.")
        return

    # deseleccionamos todo y seleccionamos los miembros del grupo
    seqs_all = bpy.context.scene.sequence_editor.sequences_all
    for s in seqs_all:
        s.select = False
    for name in members:
        s = seqs_all.get(name)
        if s:
            s.select = True
    # establecer active strip al primero
    first = members[0] if members else None
    if first and bpy.context.scene.sequence_editor:
        bpy.context.scene.sequence_editor.active_strip = bpy.context.scene.sequence_editor.sequences_all.get(first)

    print(f"OSC Grouping: Grupo '{last_gid}' seleccionado manualmente ({len(members)} miembros).")

ZOOM_STEP = 0.1
def _execute_zoom_hack(start_frame, duration):
    sequencer = bpy.context.scene.sequence_editor
    if not sequencer: return
    original_selection_names = {s.name for s in sequencer.sequences if s.select}
    original_active = sequencer.active_strip
    dummy_strip = None
    try:
        dummy_strip = sequencer.sequences.new_effect(
            name=".osc_zoom_dummy", type='COLOR', channel=1,
            frame_start=round(start_frame), frame_end=round(start_frame + duration)
        )
        bpy.ops.sequencer.select_all(action='DESELECT')
        dummy_strip.select = True
        strips_tools._focus_on_selected_strips(clear_preview_after=True)
    finally:
        if dummy_strip:
            sequencer.sequences.remove(dummy_strip)
        for strip in sequencer.sequences:
            strip.select = strip.name in original_selection_names
        sequencer.active_strip = original_active

def _reset_zoom_to_selection():
    selected_strips = bpy.context.selected_sequences
    min_start, max_end = 0, 0
    if not selected_strips:
        scene = bpy.context.scene
        min_start, max_end = scene.frame_start, scene.frame_end
    else:
        min_start = min(s.frame_final_start for s in selected_strips)
        max_end = max(s.frame_final_end for s in selected_strips)
    strips_tools._focus_on_selected_strips(clear_preview_after=True)
    state.control_state['zoom_length'] = float(max_end - min_start)
    state.control_state['zoom_level'] = 1.0
    state.control_state['zoom_start_frame'] = float(min_start)
    print(f"OSC Zoom: Referencia establecida. Length={state.control_state['zoom_length']}, Level=1.0")

def _handle_zoom_step(direction):
    if state.control_state.get('zoom_level') is None:
        _reset_zoom_to_selection()
        return
    level = state.control_state['zoom_level']
    length = state.control_state['zoom_length']
    start_frame = state.control_state['zoom_start_frame']
    min_level = 1.0 / length if length > 0 else 0.05
    new_level = level + (ZOOM_STEP * direction)
    new_level = max(min_level, new_level)
    target_duration = length * new_level
    new_start_frame = 0.0
    selected_strips = bpy.context.selected_sequences
    if state.control_state.get('shift_active', False):
        center_point = float(bpy.context.scene.frame_current)
        new_start_frame = center_point - (target_duration / 2)
        state.control_state['zoom_start_frame'] = new_start_frame
    else:
        if not selected_strips:
            previous_center = start_frame + (length * level) / 2.0
            new_start_frame = previous_center - (target_duration / 2)
        else:
            min_sel_start = min(s.frame_final_start for s in selected_strips)
            max_sel_end = max(s.frame_final_end for s in selected_strips)
            center_of_selection = min_sel_start + (max_sel_end - min_sel_start) / 2.0
            previous_duration = length * level
            previous_center = start_frame + previous_duration / 2.0
            pan_distance = center_of_selection - previous_center
            eased_pan_offset = pan_distance / 3.0
            new_center = previous_center + eased_pan_offset
            new_start_frame = new_center - (target_duration / 2)
            state.control_state['zoom_start_frame'] = new_start_frame
    state.control_state['zoom_level'] = new_level
    _execute_zoom_hack(new_start_frame, target_duration)

def apply_preview_tag(strip):
    if strip: strip.color_tag = 'COLOR_03'
def remove_preview_tag(strip):
    if strip and strip.color_tag == 'COLOR_03':
        strip.color_tag = 'NONE'

def update_preview_strip(new_strip):
    previous_strip_name = state.control_state.get("preview_strip_name")
    if previous_strip_name:
        previous_strip = bpy.context.scene.sequence_editor.sequences_all.get(previous_strip_name)
        if previous_strip: remove_preview_tag(previous_strip)
    if new_strip:
        apply_preview_tag(new_strip)
        state.control_state["preview_strip_name"] = new_strip.name
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current = new_strip.frame_final_start
    else:
        state.control_state["preview_strip_name"] = None

    _ensure_active_strip(state.control_state.get("preview_strip_name"))

def _maybe_follow_preview():
    nav = state.control_state.get('strip_nav_active', False)
    follow = state.control_state.get('strip_nav_follow_active', False)
    preview_name = state.control_state.get("preview_strip_name")
    if not (nav and follow) or not preview_name: return
    strip_obj = bpy.context.scene.sequence_editor.sequences_all.get(preview_name)
    if not strip_obj: return
    try:
        bpy.context.scene.frame_current = strip_obj.frame_final_start
    except Exception as e:
        print(f"[follow] Error moviendo playhead: {e}")

def _send_open_filters_feedback():
    """
    Función placeholder para enviar el mensaje OSC que abre el menú de filtros.
    """
    print("OSC VSE: No hay más candidatos. Enviando señal para abrir filtros.")
    osc_feedback.send("/strip_filter", True)

def _find_absolute_next_strip(current_strip, direction):
    """
    Busca el siguiente/anterior strip disponible en toda la secuencia (fallback universal).
    Ordena por frame de inicio y luego por canal.
    Devuelve un strip o None si no hay más candidatos.
    """
    all_strips = _get_globally_filtered_strips()
    # Si solo hay un strip o menos, no hay a dónde ir.
    if not all_strips or len(all_strips) <= 1:
        return None

    # Ordenar por frame de inicio, y como desempate, por canal
    sorted_strips = sorted(all_strips, key=lambda s: (s.frame_final_start, s.channel))

    try:
        current_index = sorted_strips.index(current_strip)
        next_index = (current_index + direction) % len(sorted_strips)
        return sorted_strips[next_index]
    except ValueError:
        # Si el strip actual no está en la lista (raro), devolver el primero/último
        return sorted_strips[0] if direction == 1 else sorted_strips[-1]

def _ensure_active_strip(preview_name=None):
    """
    Garantiza que el sequence_editor tenga un active_strip válido.
    - Prioridad 1: preview_strip_name (si existe y sigue en la escena).
    - Prioridad 2: primer strip en selection_set.
    """
    seq_editor = bpy.context.scene.sequence_editor
    if not seq_editor:
        return
    if preview_name and preview_name in seq_editor.sequences_all:
        seq_editor.active_strip = seq_editor.sequences_all[preview_name]
    else:
        sel_set = state.control_state.get("selection_set", set())
        for name in sel_set:
            if name in seq_editor.sequences_all:
                seq_editor.active_strip = seq_editor.sequences_all[name]
                break

def _navigate_preview_horizontal(direction):
    current_strip_name = state.control_state.get("preview_strip_name")
    if not current_strip_name: return

    current_strip = bpy.context.scene.sequence_editor.sequences_all.get(current_strip_name)
    if not current_strip: return

    target_strip = None
    all_strips = _get_globally_filtered_strips()
    if not all_strips: return

    # --- LÓGICA PRIORITARIA: Mismo canal ---
    strips_on_channel = sorted(
        [s for s in all_strips if s.channel == current_strip.channel],
        key=lambda s: s.frame_final_start
    )

    if strips_on_channel:
        try:
            current_index = strips_on_channel.index(current_strip)
            next_index = current_index + direction

            # Comprobar si el índice está dentro de los límites del canal actual
            if 0 <= next_index < len(strips_on_channel):
                target_strip = strips_on_channel[next_index]
        except ValueError:
            # El strip actual no está en la lista filtrada, encontrar el más cercano en el canal
            if direction == 1: # Hacia adelante
                candidates = [s for s in strips_on_channel if s.frame_final_start > current_strip.frame_final_start]
                if candidates: target_strip = candidates[0]
            else: # Hacia atrás
                candidates = [s for s in strips_on_channel if s.frame_final_start < current_strip.frame_final_start]
                if candidates: target_strip = candidates[-1]

    # --- FALLBACK: Si no se encontró candidato en el mismo canal, buscar en toda la secuencia ---
    if target_strip is None:
        print("Fallback horizontal: buscando en todos los canales...")
        target_strip = _find_absolute_next_strip(current_strip, direction)

    # --- APLICAR RESULTADO Y FALLBACK FINAL ---
    if target_strip and target_strip != current_strip:
        update_preview_strip(target_strip)
        _maybe_follow_preview()
    elif len(all_strips) <= 1:
        _send_open_filters_feedback()

def _navigate_preview_vertical(direction):
    current_strip_name = state.control_state.get("preview_strip_name")
    if not current_strip_name: return

    current_strip = bpy.context.scene.sequence_editor.sequences_all.get(current_strip_name)
    if not current_strip: return

    target_strip = None
    all_strips = _get_globally_filtered_strips()
    if not all_strips: return

    # --- priorizar strip activo, si no, playhead ---
    active_strip = bpy.context.scene.sequence_editor.active_strip
    if active_strip and active_strip.select:
        reference_frame = active_strip.frame_final_start
    else:
        reference_frame = bpy.context.scene.frame_current

    # --- LÓGICA PRIORITARIA: Buscar en canales adyacentes ---
    available_channels = sorted(list(set(s.channel for s in all_strips)))

    try:
        # Encontrar el índice del canal actual en la lista de canales disponibles
        current_channel_index = available_channels.index(current_strip.channel)
        next_channel_index = current_channel_index + direction

        # Buscar iterativamente en la dirección vertical a través de canales con contenido
        while 0 <= next_channel_index < len(available_channels):
            target_channel = available_channels[next_channel_index]
            strips_on_target_channel = [s for s in all_strips if s.channel == target_channel]

            if strips_on_target_channel:
                # Encontrar el strip más cercano en tiempo a nuestro frame de referencia
                target_strip = min(strips_on_target_channel, key=lambda s: abs(s.frame_final_start - reference_frame))
                break # ¡Candidato encontrado! Salir del bucle.

            next_channel_index += direction # Probar el siguiente canal disponible
    except ValueError:
        pass # El canal actual no está en la lista, el fallback se encargará.

    # --- FALLBACK: Si no se encontró candidato vertical, usar el fallback absoluto ---
    if target_strip is None:
        print("Fallback vertical: buscando en toda la secuencia...")
        # Usamos la dirección horizontal como un análogo razonable para "siguiente/anterior"
        horizontal_direction = 1 if direction == -1 else -1 # Arriba (-1) -> Siguiente (1), Abajo (1) -> Anterior (-1)
        target_strip = _find_absolute_next_strip(current_strip, horizontal_direction)

    # --- APLICAR RESULTADO Y FALLBACK FINAL ---
    if target_strip and target_strip != current_strip:
        update_preview_strip(target_strip)
        _maybe_follow_preview()
    elif len(all_strips) <= 1:
        _send_open_filters_feedback()

def _navigate_preview_by_jog(jog_value):
    abs_val = abs(jog_value)
    if abs_val < 0.01: return
    if abs_val > 0.61: cooldown = 0.1
    elif abs_val > 0.31: cooldown = 0.25
    else: cooldown = 0.5
    if time.time() - state.control_state.get('last_nav_time', 0.0) > cooldown:
        direction = 1 if jog_value > 0 else -1
        _navigate_preview_horizontal(direction)
        state.control_state['last_nav_time'] = time.time()

def get_active_filter_types():
    osc_props = bpy.context.scene.osc_vse_properties
    allowed_types = set()
    if osc_props.filter_movie: allowed_types.add('MOVIE')
    if osc_props.filter_image: allowed_types.add('IMAGE')
    if osc_props.filter_meta: allowed_types.add('META')
    if osc_props.filter_color: allowed_types.add('COLOR')
    if osc_props.filter_text: allowed_types.add('TEXT')
    if osc_props.filter_adjustment: allowed_types.add('ADJUSTMENT')
    if osc_props.filter_effect_speed: allowed_types.add('SPEED')
    if osc_props.filter_effect_transform: allowed_types.add('TRANSFORM')
    if osc_props.filter_transitions:
        allowed_types.update({'CROSS','ADD','SUBTRACT','ALPHA_OVER','ALPHA_UNDER','GAMMA_CROSS','MULTIPLY','OVER_DROP','WIPE'})
    if osc_props.filter_scene: allowed_types.add('SCENE')
    if osc_props.filter_clip: allowed_types.add('CLIP')
    if osc_props.filter_mask: allowed_types.add('MASK')
    if hasattr(osc_props, "filter_audio") and osc_props.filter_audio:
        allowed_types.add('SOUND')
    if hasattr(osc_props, "filter_glow") and osc_props.filter_glow:
        allowed_types.add('GLOW')
    if hasattr(osc_props, "filter_blur") and osc_props.filter_blur:
        allowed_types.add('GAUSSIAN_BLUR')

    return allowed_types

def _get_globally_filtered_strips():
    all_sequences = bpy.context.scene.sequence_editor.sequences_all
    allowed_types = get_active_filter_types()
    if not allowed_types: return []
    return [s for s in all_sequences if s.type in allowed_types]

def get_strips_at_frame(frame):
    filtered_strips = _get_globally_filtered_strips()
    strips = [s for s in filtered_strips if s.frame_final_start <= frame < s.frame_final_end]
    return sorted(strips, key=lambda s: s.channel)

def get_nearest_strip_to_frame(frame):
    sequences = _get_globally_filtered_strips()
    if not sequences: return None
    return min(sequences, key=lambda s: min(abs(s.frame_final_start - frame), abs(s.frame_final_end - frame)))

def cancel_strip_time_timer():
    timer_func = state.control_state.get("strip_time_timer")
    if timer_func and bpy.app.timers.is_registered(timer_func):
        bpy.app.timers.unregister(timer_func)
    state.control_state["strip_time_timer"] = None

def select_all_filtered_strips_action():
    bpy.ops.ed.undo_push(message="OSC Select All Filtered")
    for strip in _get_globally_filtered_strips(): strip.select = True
    state.control_state["strip_time_timer"] = None
    return None

_filter_map = {
    "/movie": "filter_movie", "/image": "filter_image", "/meta": "filter_meta",
    "/color": "filter_color", "/text": "filter_text", "/adjust": "filter_adjustment",
    "/speed": "filter_effect_speed", "/trans": "filter_transitions", "/scene": "filter_scene",
    "/tranf": "filter_effect_transform", "/mask": "filter_mask", "/clip": "filter_clip", "/audio": "filter_audio","/glow": "filter_glow","/blur": "filter_blur",
}

def handle_filter_toggle(address, args):
    if not args or not isinstance(args[0], bool): return
    setattr(bpy.context.scene.osc_vse_properties, _filter_map[address], args[0])

def handle_fcur_tag(address, args):
    if not args: return
    val = args[0]
    result = None
    try: result = bool(val)
    except Exception: return
    state.control_state['strip_nav_follow_active'] = result
    if result and state.control_state.get('strip_nav_active', False):
        _maybe_follow_preview()

def handle_strip_selection(address, args):
    if not args or not isinstance(args[0], bool): return
    is_pressed = args[0]
    if is_pressed:
        current_time = time.time()
        # Lógica para "Doble Clic"
        if current_time - state.control_state.get('last_vstrip_press_time', 0.0) < 0.4:
            cancel_strip_time_timer()
            bpy.ops.sequencer.select_all(action='DESELECT')
            state.control_state.get('selection_set', set()).clear()

            strips_under_playhead = get_strips_at_frame(bpy.context.scene.frame_current)
            target_strip = strips_under_playhead[0] if strips_under_playhead else get_nearest_strip_to_frame(bpy.context.scene.frame_current)

            if target_strip:
                target_strip.select = True

                # <-- INICIO: NUEVA LÓGICA DE SELECCIÓN DE GRUPO -->
                # Comprueba si la opción de seleccionar grupo está activa
                if state.control_state.get('select_grouped_on_exit', False):
                    # Si es así, expande la selección al grupo completo
                    groups_logic.expand_selection_to_groups()

                # Sincroniza nuestro 'selection_set' con lo que realmente está seleccionado en Blender
                selection_set = state.control_state.get('selection_set')
                selection_set.clear()
                for s in bpy.context.selected_sequences:
                    selection_set.add(s.name)
                # <-- FIN: NUEVA LÓGICA DE SELECCIÓN DE GRUPO -->

            update_preview_strip(None)
            _ensure_active_strip(state.control_state.get("preview_strip_name"))

        # Lógica para "Un Clic" (sin cambios)
        else:
            state.control_state['strip_nav_active'] = True
            osc_feedback.send_active_tool_feedback()
            state.control_state['selection_set'].clear()
            bpy.ops.sequencer.select_all(action='DESELECT')
            bpy.ops.ed.undo_push(message="OSC Nav Start")
            strips_under_playhead = get_strips_at_frame(bpy.context.scene.frame_current)
            if strips_under_playhead:
                initial_strip = strips_under_playhead[0]
            else:
                initial_strip = get_nearest_strip_to_frame(bpy.context.scene.frame_current)
            update_preview_strip(initial_strip)
            state.control_state["strip_time_timer"] = select_all_filtered_strips_action
            bpy.app.timers.register(select_all_filtered_strips_action, first_interval=3.0)

        state.control_state['last_vstrip_press_time'] = current_time

    # Lógica al soltar el botón (sin cambios)
    else:
        if state.control_state.get('strip_nav_active', False):
            state.control_state['strip_nav_active'] = False
            osc_feedback.send_active_tool_feedback()
            cancel_strip_time_timer()
            update_preview_strip(None)
            _clear_all_group_colors()
            if state.control_state.get('select_grouped_on_exit', False):
                groups_logic.expand_selection_to_groups()

def handle_set_selection(address, args):
    if not args or not args[0]: return
    cancel_strip_time_timer()
    if not state.control_state.get('strip_nav_active', False): return
    strip_name_to_toggle = state.control_state.get("preview_strip_name")
    if not strip_name_to_toggle: return
    selection_set = state.control_state["selection_set"]
    strip_obj = bpy.context.scene.sequence_editor.sequences_all.get(strip_name_to_toggle)
    if not strip_obj: return
    if strip_name_to_toggle in selection_set:
        selection_set.remove(strip_name_to_toggle)
        strip_obj.select = False
    else:
        selection_set.add(strip_name_to_toggle)
        strip_obj.select = True
    for s in bpy.context.scene.sequence_editor.sequences_all:
        s.select = (s.name in selection_set)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()
    for s in bpy.context.scene.sequence_editor.sequences_all:
        s.select = (s.name in selection_set)

    _ensure_active_strip(state.control_state.get("preview_strip_name"))

    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()

def handle_cur_strip(address, args):
    selected_strips = bpy.context.selected_sequences
    if not selected_strips: return
    target_strip = selected_strips[0]
    if state.control_state.get("shift_active", False):
        bpy.context.scene.frame_current = target_strip.frame_final_end
    else:
        bpy.context.scene.frame_current = target_strip.frame_final_start

def handle_blend_mode_cycle(address, *args):
    selected_strips = [s for s in bpy.context.selected_sequences if hasattr(s, 'blend_type')]
    if not selected_strips: return
    active_strip = bpy.context.scene.sequence_editor.active_strip
    if not active_strip or active_strip not in selected_strips:
        active_strip = selected_strips[0]
    try:
        blend_type_prop = active_strip.bl_rna.properties['blend_type']
        mode_list = [item.identifier for item in blend_type_prop.enum_items]
    except (AttributeError, KeyError): return
    bpy.ops.ed.undo_push(message="OSC Blend Mode Change")
    if address == "/sync_blend":
        sync_mode = active_strip.blend_type
        for strip in selected_strips:
            strip.blend_type = sync_mode
        osc_feedback.send("/blend_feedback", sync_mode)
        return
    for strip in selected_strips:
        strip.blend_type = active_strip.blend_type
    try:
        current_index = mode_list.index(active_strip.blend_type)
    except ValueError:
        current_index = 0
    direction = 1 if address == "/nblend" else -1
    new_index = (current_index + direction) % len(mode_list)
    new_mode = mode_list[new_index]
    for strip in selected_strips:
        strip.blend_type = new_mode
    osc_feedback.send("/blend_feedback", new_mode)

def handle_delete_from_selection_set(address, args):
    if not args or not args[0]: return
    if not state.control_state.get('strip_nav_active', False): return
    if bpy.context.selected_sequences:
        bpy.ops.ed.undo_push(message="OSC Delete Selected Strips")
        bpy.ops.sequencer.delete()

@persistent
def sync_selection_set_with_scene(scene):
    selection_set = state.control_state.get('selection_set')
    if not selection_set: return
    all_strip_names = {s.name for s in scene.sequence_editor.sequences_all}
    strips_to_remove = {name for name in selection_set if name not in all_strip_names}
    if strips_to_remove:
        selection_set.difference_update(strips_to_remove)

def register(): pass
def unregister(): pass
def register_actions(): pass