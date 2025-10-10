# strips_advance.py

import bpy
import math
import time
from . import state
from . import groups_logic
from . import adds
from . import osc_feedback # <-- AÑADIDO

# --- Funciones Auxiliares ---

def _find_completely_empty_channel(sequencer, start_frame=None, end_frame=None):
    """
    Escanea el VSE y devuelve el número del primer canal que no contiene ningún strip.
    Si se provee start_frame y end_frame, busca un canal vacío en ese rango de tiempo.
    """
    used_channels = set()
    for s in sequencer.sequences_all:
        if start_frame is not None and end_frame is not None:
            # Comprobar si hay solapamiento
            if max(_get_visible_range(s)[0], start_frame) < min(_get_visible_range(s)[1], end_frame):
                used_channels.add(s.channel)
        else:
            used_channels.add(s.channel)

    channel = 1
    while True:
        if channel not in used_channels:
            return channel
        channel += 1

def _get_visible_range(strip):
    """
    Devuelve el rango visible (start, end) de un strip.
    Considera offsets si existen.
    """
    if hasattr(strip, "frame_final_start") and hasattr(strip, "frame_final_end"):
        return int(strip.frame_final_start), int(strip.frame_final_end)
    else:
        start = int(strip.frame_start)
        end = int(strip.frame_start + getattr(strip, "frame_duration", strip.frame_final_duration if hasattr(strip, "frame_final_duration") else 0))
        return start, end

# --- Lógica de Reposicionamiento ---

def _recalculate_layout_forward(gap, initial_states):
    """Calcula el layout con ancla al inicio."""
    target_vis_start = {}
    if not initial_states:
        return target_vis_start

    # El ancla es el inicio visible del primer strip.
    target_vis_start[initial_states[0]['name']] = initial_states[0]['vis_start']
    current_position = float(initial_states[0]['vis_end'])

    for i in range(1, len(initial_states)):
        sd = initial_states[i]
        new_vis_start = current_position + gap
        floored_start = math.floor(new_vis_start)
        target_vis_start[sd['name']] = int(floored_start)
        current_position = float(floored_start + sd['duration'])

    return target_vis_start

def _recalculate_layout_backward(gap, initial_states):
    """Calcula el layout con ancla al final."""
    target_vis_start = {}
    if not initial_states:
        return target_vis_start

    n = len(initial_states)
    last_strip_data = initial_states[n-1]

    # El ancla es el inicio visible del último strip.
    target_vis_start[last_strip_data['name']] = last_strip_data['vis_start']
    current_position = float(last_strip_data['vis_start'])

    # Iterar hacia atrás desde el penúltimo al primero.
    for i in range(n - 2, -1, -1):
        sd = initial_states[i]
        new_vis_end = current_position - gap
        new_vis_start = new_vis_end - sd['duration']
        floored_start = math.floor(new_vis_start)
        target_vis_start[sd['name']] = int(floored_start)
        current_position = float(floored_start)

    return target_vis_start

# --- Lógica del Jog ---

def perform_ripple_from_jog(jog_value):
    """Manejador para la interacción del jog con la herramienta ripple."""
    if 'ripple' not in state.control_state.get('active_tools', set()):
        return

    # 1. Determinar signo y gestionar cruce por cero
    current_sign = 0
    if jog_value > 0.1: current_sign = 1
    elif jog_value < -0.1: current_sign = -1

    if current_sign != state.control_state.get('ripple_sign_state', 0):
        state.control_state['ripple_sign_state'] = current_sign

    # 2. Mapear valor del jog a un porcentaje de gap
    percentage = 1.0
    if jog_value <= -0.9:
        percentage = 0.0
    elif jog_value < -0.1:
        percentage = 1.0 - ((abs(jog_value) - 0.1) / 0.8)

    elif jog_value >= 0.9:
        percentage = 0.0
    elif jog_value > 0.1:
        percentage = 1.0 - ((jog_value - 0.1) / 0.8)

    # 3. Calcular gap actual
    initial_gap = state.control_state.get('ripple_initial_gap', 0)
    current_gap = math.floor(initial_gap * percentage)

    # 4. Recalcular y aplicar layout
    initial_states = state.control_state.get('ripple_initial_states', [])
    if not initial_states:
        return

    sign_state = state.control_state.get('ripple_sign_state', 0)
    if sign_state < 0:
        # Halar hacia adelante
        target_vis_start = _recalculate_layout_forward(current_gap, initial_states)
        # Aplicar de izquierda a derecha
        iterator = initial_states
    elif sign_state > 0:
        # Empujar hacia atrás
        target_vis_start = _recalculate_layout_backward(current_gap, initial_states)
        # Aplicar de derecha a izquierda (penúltimo → primero)
        iterator = list(reversed(initial_states[:-1]))
    else:
        # Estado neutro: layout original
        initial_gap = state.control_state.get('ripple_initial_gap', 0)
        target_vis_start = _recalculate_layout_forward(initial_gap, initial_states)
        iterator = initial_states

    # 5. Aplicar posiciones directamente
    for sd in iterator:
        strip = sd['strip']
        if strip.name in target_vis_start:
            desired_vis = target_vis_start[sd['name']]
            offset = sd['offset_start']
            new_frame_start = max(0, int(desired_vis - offset))
            strip.frame_start = new_frame_start

    # Aplicar también el último (solo si está en target)
    last = initial_states[-1]
    if last['name'] in target_vis_start:
        strip = last['strip']
        desired_vis = target_vis_start[last['name']]
        offset = last['offset_start']
        new_frame_start = max(0, int(desired_vis - offset))
        strip.frame_start = new_frame_start

# --- Manejador Principal ---

def handle_ripple_activation(address, args):
    """
    Fase 1: Activa, calcula y aplica el espaciado promedio inicial de forma segura.
    """
    if not args or not isinstance(args[0], bool):
        return

    is_pressed = args[0]

    if is_pressed:
        sequencer = bpy.context.scene.sequence_editor
        if not sequencer: return

        selected_strips = [s for s in sequencer.sequences if s.select]
        if len(selected_strips) < 2:
            print("OSC Ripple Tool: Se necesitan al menos 2 strips seleccionados.")
            return

        bpy.ops.ed.undo_push(message="OSC Ripple Tool")

        strips_sorted = sorted(selected_strips, key=lambda s: _get_visible_range(s)[0])

        initial_states = []
        for strip in strips_sorted:
            vis_start, vis_end = _get_visible_range(strip)
            initial_states.append({
                'strip': strip, 'name': strip.name,
                'vis_start': int(vis_start), 'vis_end': int(vis_end),
                'duration': int(vis_end - vis_start),
                'offset_start': int(getattr(strip, "frame_offset_start", 0)),
                'orig_frame_start': int(strip.frame_start),
                'orig_channel': int(strip.channel)
            })

        state.control_state['ripple_initial_states'] = initial_states

        total_gap_space = 0
        for i in range(1, len(initial_states)):
            gap = initial_states[i]['vis_start'] - initial_states[i-1]['vis_end']
            total_gap_space += gap

        num_gaps = len(initial_states) - 1
        average_gap_float = max(0, (total_gap_space / num_gaps) if num_gaps > 0 else 0)
        uniform_gap = math.floor(average_gap_float)

        state.control_state['ripple_initial_gap'] = uniform_gap
        state.control_state['ripple_sign_state'] = 0

        target_vis_start = _recalculate_layout_forward(uniform_gap, initial_states)

        temp_channel = _find_completely_empty_channel(sequencer)

        dest_channel = initial_states[0]['orig_channel']

        for sd in initial_states:
            strip = sd['strip']
            desired_vis = target_vis_start[sd['name']]
            offset = sd['offset_start']
            new_frame_start = max(0, int(desired_vis - offset))
            strip.frame_start = new_frame_start
            strip.channel = temp_channel

        for sd in initial_states:
            sd['strip'].channel = dest_channel

        state.control_state['active_tools'].add('ripple')
        osc_feedback.send_active_tool_feedback() # <-- MODIFICADO
        print(f"OSC Ripple Tool: ACTIVADA. uniform_gap={uniform_gap}")

    else:
        if 'ripple' in state.control_state.get('active_tools', set()):
            state.control_state['active_tools'].discard('ripple')
            osc_feedback.send_active_tool_feedback() # <-- MODIFICADO
            print("OSC Ripple Tool: DESACTIVADA.")

# --- INICIO: Implementación de la Herramienta SPLICE ---

def _find_empty_adjacent_channel(strip, direction, start_frame, end_frame):
    """Encuentra un canal adyacente vacío para un strip específico."""
    sequencer = bpy.context.scene.sequence_editor
    target_channel = strip.channel + direction
    if target_channel <= 0: return None

    for s in sequencer.sequences_all:
        if s.channel == target_channel:
            # Comprobar si hay solapamiento en el rango de tiempo
            if max(_get_visible_range(s)[0], start_frame) < min(_get_visible_range(s)[1], end_frame):
                return None # Canal ocupado
    return target_channel

def _check_strip_affinity(strip_a, strip_b):
    """Comprueba si dos strips son del mismo origen (filepath)."""
    path_a = getattr(strip_a, 'filepath', None)
    path_b = getattr(strip_b, 'filepath', None)
    # Considerar afines los strips sin filepath (Color, Text, etc.)
    if path_a is None and path_b is None and strip_a.type == strip_b.type:
        return True
    return path_a is not None and path_a == path_b

def _apply_crossfade_keyframes(preceding, rippled, overlap_duration):
    """Aplica keyframes de opacidad y/o volumen para crear un crossfade,
    forzando interpolación lineal y limpiando keyframes previos."""
    if not preceding or not rippled or overlap_duration <= 0: return

    # --- LÓGICA CORREGIDA ---
    # El inicio de la transición es el primer frame del clip de la derecha.
    start_frame = _get_visible_range(rippled)[0]
    # El fin de la transición es el ÚLTIMO frame visible del clip de la izquierda.
    end_frame = _get_visible_range(preceding)[1] - 1

    # Si no hay un rango real para la transición, limpiar y salir.
    if start_frame >= end_frame:
        _clear_crossfade_keyframes([preceding, rippled])
        return

    def apply_safe_keyframes(strip, prop_name, start_val, end_val):
        if not hasattr(strip, prop_name):
            return

        # 1. Limpiar keyframes antiguos en el rango de la nueva transición
        try:
            if strip.animation_data and strip.animation_data.action:
                fcurve = strip.animation_data.action.fcurves.find(prop_name)
                if fcurve:
                    points_to_remove = [
                        p for p in fcurve.keyframe_points
                        if start_frame <= p.co.x <= end_frame
                    ]
                    for p in reversed(points_to_remove):
                        fcurve.keyframe_points.remove(p)
        except AttributeError:
            pass # Ignorar si el strip no tiene animation_data (ej. SoundStrip)
        except Exception:
            pass # Falla silenciosamente

        # 2. Insertar nuevos keyframes
        try:
            setattr(strip, prop_name, start_val)
            strip.keyframe_insert(data_path=prop_name, frame=start_frame)

            setattr(strip, prop_name, end_val)
            strip.keyframe_insert(data_path=prop_name, frame=end_frame)

            # 3. Forzar interpolación LINEAL para una transición constante
            if strip.animation_data and strip.animation_data.action:
                fcurve = strip.animation_data.action.fcurves.find(prop_name)
                if fcurve:
                    for kp in fcurve.keyframe_points:
                        if math.isclose(kp.co.x, start_frame) or math.isclose(kp.co.x, end_frame):
                            kp.interpolation = 'LINEAR'
                    fcurve.update()

        except Exception as e:
            print(f"Error al aplicar keyframe a '{strip.name}' en '{prop_name}': {e}")

    # Aplicar a las propiedades de alpha y volumen
    apply_safe_keyframes(preceding, 'blend_alpha', 1.0, 0.0)
    apply_safe_keyframes(rippled, 'blend_alpha', 0.0, 1.0)

    apply_safe_keyframes(preceding, 'volume', 1.0, 0.0)
    apply_safe_keyframes(rippled, 'volume', 0.0, 1.0)

def _clear_crossfade_keyframes(strips):
    """Elimina los keyframes de un crossfade y restaura los valores por defecto."""
    if not strips: return

    for strip in strips:
        if not strip: continue

        # Restaurar valores por defecto (esto es seguro para todos los strips)
        if hasattr(strip, 'blend_alpha'):
            strip.blend_alpha = 1.0
        if hasattr(strip, 'volume'):
            strip.volume = 1.0

        # Intentar eliminar las curvas de animación de forma segura,
        # capturando el error si el strip no soporta animation_data.
        try:
            if strip.animation_data and strip.animation_data.action:
                action = strip.animation_data.action

                fcurves_to_remove = []
                if hasattr(strip, 'blend_alpha'):
                    fc = action.fcurves.find('blend_alpha')
                    if fc: fcurves_to_remove.append(fc)
                if hasattr(strip, 'volume'):
                    fc = action.fcurves.find('volume')
                    if fc: fcurves_to_remove.append(fc)

                for fc in reversed(fcurves_to_remove):
                    action.fcurves.remove(fc)
        except AttributeError:
            # Falla silenciosamente si el strip (ej. SoundStrip) no tiene
            # el atributo 'animation_data'. Esto es esperado y correcto.
            pass

def handle_splice_tool(address, args):
    """Handler principal para la herramienta SPLICE (modelo híbrido)."""
    if not args or not isinstance(args[0], bool): return
    is_pressed = args[0]
    tool_name = "splice_trim"
    sequencer = bpy.context.scene.sequence_editor

    if is_pressed:
        if not sequencer or not bpy.context.selected_sequences: return
        bpy.ops.ed.undo_push(message="OSC Splice")

        # --- FASE 1: Universal (Corte, Borrado, Ripple) ---
        target_strips_orig = list(bpy.context.selected_sequences)
        target_names = {s.name for s in target_strips_orig}

        # Aislar selección
        bpy.ops.sequencer.select_all(action='DESELECT')
        for s in sequencer.sequences_all:
            if s.name in target_names: s.select = True

        strips_to_cut = list(bpy.context.selected_sequences)
        if not strips_to_cut: return bpy.ops.ed.undo()

        # Snapshot para identificar supervivientes
        names_before_cut = {s.name for s in sequencer.sequences_all}

        # Corte y medición
        cut_frame = bpy.context.scene.frame_current
        override_context = adds.get_sequencer_context()
        if not override_context: return bpy.ops.ed.undo()

        with bpy.context.temp_override(**override_context):
            bpy.ops.sequencer.split(frame=cut_frame, type='HARD', side='LEFT')

        bad_take_strips = list(bpy.context.selected_sequences)
        if not bad_take_strips: # No se creó nada a la izquierda
            print("OSC SPLICE: El corte no produjo un segmento para borrar.")
            bpy.ops.sequencer.select_all(action='DESELECT') # Limpiar selección
            for name in target_names: # Restaurar selección original
                s = sequencer.sequences_all.get(name)
                if s: s.select = True
            return bpy.ops.ed.undo()

        deleted_duration = _get_visible_range(bad_take_strips[0])[1] - _get_visible_range(bad_take_strips[0])[0]

        bpy.ops.sequencer.delete()
        bpy.context.view_layer.update()

        survivor_strips = [s for s in sequencer.sequences_all if s.name not in names_before_cut]
        for strip in survivor_strips:
            strip.frame_start -= deleted_duration

        bpy.ops.sequencer.select_all(action='DESELECT')
        for s in survivor_strips: s.select = True
        if survivor_strips: sequencer.active_strip = survivor_strips[0]

        if state.control_state.get("auto_mirror", False) and len(survivor_strips) >= 2:
            groups_logic.auto_mirror_birth_from_cut(survivor_strips)

        # --- FASE 2: Condicional (Preparación del Modo Interactivo) ---
        interactive_mode_possible = len(target_strips_orig) in [1, 2]
        if not interactive_mode_possible: return

        gap_start_frame = _get_visible_range(survivor_strips[0])[0] if survivor_strips else 0
        preceding_strips = [s for s in sequencer.sequences_all if s not in survivor_strips and math.isclose(_get_visible_range(s)[1], gap_start_frame)]

        if not preceding_strips:
            print("OSC SPLICE: No hay strip precedente para el ajuste fino.")
            return

        move_plan = {}
        can_move_all = True
        strips_for_check = survivor_strips if len(target_strips_orig) == 2 else [survivor_strips[0], preceding_strips[0]]

        for strip in strips_for_check:
            start, end = _get_visible_range(strip)
            safe_ch = _find_empty_adjacent_channel(strip, 1, start-10, end+10) or _find_empty_adjacent_channel(strip, -1, start-10, end+10)
            if safe_ch is None:
                can_move_all = False
                break
            move_plan[strip.name] = {'safe': safe_ch, 'original': strip.channel}

        if not can_move_all or len(move_plan) != len(strips_for_check):
             print("OSC SPLICE: No se encontraron canales de maniobra para todos los strips.")
             return

        context_data = {
            'move_plan': move_plan,
            'preceding_names': [s.name for s in preceding_strips],
            'rippled_names': [s.name for s in survivor_strips],
            'crossfade_active': False,
            'interactive_started': False
        }
        state.control_state['splice_trim_context'] = context_data
        state.control_state['active_tools'].add(tool_name)
        osc_feedback.send_active_tool_feedback() # <-- MODIFICADO
        print("OSC SPLICE: Modo de ajuste fino activado.")

    else: # Al soltar el botón
        if tool_name in state.control_state.get('active_tools', set()):
            context = state.control_state.get('splice_trim_context', {})

            if context and sequencer:
                move_plan = context.get('move_plan', {})
                rippled_names = context.get('rippled_names', [])
                preceding_names = context.get('preceding_names', [])

                rippled_strips = [sequencer.sequences_all.get(n) for n in rippled_names if sequencer.sequences_all.get(n)]
                preceding_strips = [sequencer.sequences_all.get(n) for n in preceding_names if sequencer.sequences_all.get(n)]

                # Recalcular parejas y overlap final
                pairs = []
                unmatched_rippled = list(rippled_strips)
                for p_strip in preceding_strips:
                    best_match = next((r for r in unmatched_rippled if _check_strip_affinity(p_strip, r)), None)
                    if best_match:
                        pairs.append((p_strip, best_match))
                        unmatched_rippled.remove(best_match)
                if not pairs and preceding_strips and rippled_strips:
                    pairs.append((preceding_strips[0], rippled_strips[0]))

                final_overlap_exists = False
                for p_strip, r_strip in pairs:
                    p_end = _get_visible_range(p_strip)[1]
                    r_start = _get_visible_range(r_strip)[0]
                    if r_start < p_end:
                        final_overlap_exists = True
                        overlap = p_end - r_start
                        _apply_crossfade_keyframes(p_strip, r_strip, overlap)

                if final_overlap_exists:
                    print("OSC SPLICE: Crossfade final aplicado.")
                else:
                    _clear_crossfade_keyframes(preceding_strips + rippled_strips)

                for name, data in move_plan.items():
                    strip = sequencer.sequences_all.get(name)
                    if strip: strip.channel = data['original']

            state.control_state['active_tools'].discard(tool_name)
            if 'splice_trim_context' in state.control_state:
                del state.control_state['splice_trim_context']

            osc_feedback.send_active_tool_feedback() # <-- MODIFICADO
            print("OSC SPLICE: Modo de ajuste fino desactivado.")

def _perform_splice_trim_from_jog(jog_value):
    _perform_splice_trim_movement(jog_value * 5)

def _perform_splice_trim_from_nudge(direction):
    _perform_splice_trim_movement(direction)

def _perform_splice_trim_movement(delta_frames):
    """Lógica central de movimiento para la herramienta SPLICE.
    SOLO mueve los strips y el cabezal, no aplica ninguna animación."""
    context = state.control_state.get('splice_trim_context')
    sequencer = bpy.context.scene.sequence_editor
    if not context or not sequencer: return

    if not context.get('interactive_started', False):
        move_plan = context.get('move_plan', {})
        for name, data in move_plan.items():
            strip = sequencer.sequences_all.get(name)
            if strip: strip.channel = data['safe']
        context['interactive_started'] = True

    rippled_names = context.get('rippled_names', [])
    if not rippled_names: return

    rippled_strips = [sequencer.sequences_all.get(n) for n in rippled_names if sequencer.sequences_all.get(n)]

    for strip in rippled_strips:
        strip.frame_start += int(round(delta_frames))

    # --- INICIO: Lógica de Seguimiento del Cabezal ---
    if state.control_state.get('strip_nav_follow_active', False) and rippled_strips:
        # Usamos el primer strip de la derecha como referencia
        reference_strip = rippled_strips[0]
        # La posición ideal es un frame antes de que este strip comience
        target_frame = _get_visible_range(reference_strip)[0] - 1

        # Asegurarnos de no ir a un frame antes del inicio de la escena
        scene_start_frame = bpy.context.scene.frame_start
        bpy.context.scene.frame_current = max(scene_start_frame, target_frame)
    # --- FIN: Lógica de Seguimiento del Cabezal ---

# --- FIN: Implementación de la Herramienta SPLICE ---

# --- INICIO: Implementación de la Herramienta INSERT ---

def _insert_fade(strip, prop_name, start_frame, end_frame, start_val, end_val):
    """Helper para insertar un fade lineal seguro en una propiedad animable."""
    if not strip or not hasattr(strip, prop_name):
        return
    try:
        # 1. Insertar keyframes (esto crea .animation_data si es necesario)
        setattr(strip, prop_name, start_val)
        strip.keyframe_insert(data_path=prop_name, frame=start_frame)

        setattr(strip, prop_name, end_val)
        strip.keyframe_insert(data_path=prop_name, frame=end_frame)

        # 2. Forzar la actualización para que Python vea los cambios
        bpy.context.view_layer.update()

        # 3. Ahora que .animation_data existe, podemos accederlo para limpiar y ajustar.
        if strip.animation_data and strip.animation_data.action:
            fcurve = strip.animation_data.action.fcurves.find(prop_name)
            if fcurve:
                # Limpiar keyframes viejos que hayan quedado en medio
                points_to_remove = [
                    p for p in fcurve.keyframe_points
                    if not (math.isclose(p.co.x, start_frame) or math.isclose(p.co.x, end_frame))
                    and start_frame < p.co.x < end_frame
                ]
                for p in reversed(points_to_remove):
                    fcurve.keyframe_points.remove(p)

                # Ajustar interpolación de los nuevos keyframes a LINEAL
                for kp in fcurve.keyframe_points:
                    if math.isclose(kp.co.x, start_frame) or math.isclose(kp.co.x, end_frame):
                        kp.interpolation = 'LINEAR'
                fcurve.update()

    except Exception as e:
        pass

def _apply_insert_keyframes(left_strip, insert_strip, right_strip):
    """
    Aplica fundidos en un escenario de INSERT:
      - Fade-out en left_strip al inicio del insert.
      - Fade-in en right_strip al final del insert.
      - Fade-in/out en insert_strip si hay overlap real.
    """
    if not insert_strip:
        return

    _clear_crossfade_keyframes([left_strip, insert_strip, right_strip])
    insert_start, insert_end = _get_visible_range(insert_strip)

    # --- FADE OUT en el LEFT y FADE IN en el INSERT ---
    if left_strip:
        left_start, left_end = _get_visible_range(left_strip)
        overlap_in = left_end - insert_start
        if overlap_in > 1:
            start_frame = insert_start
            end_frame = left_end - 1
            if start_frame < end_frame:
                 _insert_fade(left_strip, 'blend_alpha', start_frame, end_frame, 1.0, 0.0)
                 _insert_fade(insert_strip, 'blend_alpha', start_frame, end_frame, 0.0, 1.0)

    # --- FADE OUT en el INSERT y FADE IN en el RIGHT ---
    if right_strip:
        right_start, right_end = _get_visible_range(right_strip)
        overlap_out = insert_end - right_start
        if overlap_out > 1:
            start_frame = right_start
            end_frame = insert_end - 1
            if start_frame < end_frame:
                _insert_fade(right_strip, 'blend_alpha', start_frame, end_frame, 0.0, 1.0)
                _insert_fade(insert_strip, 'blend_alpha', start_frame, end_frame, 1.0, 0.0)


def handle_insert_activation(address, args):
    """Handler principal para la herramienta INSERT."""
    if not args or not isinstance(args[0], bool): return
    is_pressed = args[0]
    tool_name = "insert"
    sequencer = bpy.context.scene.sequence_editor
    if not sequencer: return

    if is_pressed:
        bpy.ops.ed.undo_push(message="OSC Insert")
        snapshot_all_strips = {s.name for s in sequencer.sequences_all}
        initial_selection = list(bpy.context.selected_sequences)

        # --- Validación ---
        if len(initial_selection) < 2:
            print("OSC Insert: Se necesitan al menos 2 strips seleccionados.")
            return

        if len({s.channel for s in initial_selection}) != len(initial_selection):
            print("OSC Insert: Error, cada strip seleccionado debe estar en un canal único.")
            return

        sorted_selection = sorted(initial_selection, key=lambda s: s.channel)
        insert_strip = sorted_selection[-1]
        content_strips = sorted_selection[:-1]

        for cs in content_strips:
            if _get_visible_range(insert_strip)[0] <= _get_visible_range(cs)[0]:
                print(f"OSC Insert: El strip a insertar debe empezar después del contenido. Falló en '{cs.name}'.")
                return

        # --- Ejecución de Corte (con control de selección) ---
        cut_frame = _get_visible_range(insert_strip)[0]
        move_distance = _get_visible_range(insert_strip)[1] - cut_frame

        bpy.ops.sequencer.select_all(action='DESELECT')
        for strip in content_strips:
            strip.select = True
            bpy.ops.sequencer.split(frame=cut_frame, type='HARD', side='RIGHT')
            strip.select = False # Deseleccionar la parte izquierda

        # --- Desplazamiento Inicial ---
        right_side_strips = list(bpy.context.selected_sequences)
        for strip in right_side_strips:
            strip.frame_start += move_distance

        # --- Estado Modal ---
        context_data = {
            'snapshot_all_strips': snapshot_all_strips,
            'insert_strip_name': insert_strip.name,
            'left_side_names': [s.name for s in content_strips],
            'right_side_names': [s.name for s in right_side_strips],
            'insert_duration': move_distance,
            'accumulated_delta': 0.0,
        }
        state.control_state['insert_context'] = context_data
        state.control_state['active_tools'].add(tool_name)
        osc_feedback.send_active_tool_feedback() # <-- MODIFICADO
        print("OSC Insert Tool: ACTIVADA.")

    else: # Al soltar el botón
        if tool_name in state.control_state.get('active_tools', set()):
            context = state.control_state.get('insert_context', {})
            if context and sequencer:
                # --- Crossfades ---
                insert_strip = sequencer.sequences_all.get(context.get('insert_strip_name'))
                if insert_strip:
                    left_strips_unsorted = [sequencer.sequences_all.get(n) for n in context['left_side_names']]
                    right_strips_unsorted = [sequencer.sequences_all.get(n) for n in context['right_side_names']]

                    left_strips = sorted([s for s in left_strips_unsorted if s], key=lambda s: s.channel)
                    right_strips = sorted([s for s in right_strips_unsorted if s], key=lambda s: s.channel)

                    pairs = {}
                    for strip in left_strips:
                        pairs.setdefault(strip.channel, {})['left'] = strip
                    for strip in right_strips:
                        pairs.setdefault(strip.channel, {})['right'] = strip

                    fades_applied = False
                    for channel, strip_pair in pairs.items():
                        left = strip_pair.get('left')
                        right = strip_pair.get('right')
                        # Solo se aplica si hay un par completo para un canal
                        if left and right:
                             _apply_insert_keyframes(left, insert_strip, right)
                             fades_applied = True
                    if fades_applied:
                        print(f"OSC Insert: Proceso de fundidos ejecutado.")

                # --- Agrupado ---
                snapshot_all_strips = context.get('snapshot_all_strips', set())
                current_strips_names = {s.name for s in sequencer.sequences_all}
                new_strip_names = current_strips_names - snapshot_all_strips

                if new_strip_names:
                    new_strips_objects = [sequencer.sequences_all.get(n) for n in new_strip_names]
                    if len(new_strips_objects) >= 2:
                        bpy.ops.sequencer.select_all(action='DESELECT')
                        for s in new_strips_objects:
                            if s: s.select = True
                        groups_logic.auto_mirror_birth_from_cut(list(bpy.context.selected_sequences))

            # --- Limpieza ---
            state.control_state['active_tools'].discard(tool_name)
            if 'insert_context' in state.control_state:
                del state.control_state['insert_context']

            osc_feedback.send_active_tool_feedback() # <-- MODIFICADO
            print("OSC Insert Tool: DESACTIVADA.")


def _perform_insert_from_jog(jog_value):
    """Maneja el ajuste fino y fluido para la herramienta Insert."""
    delta = jog_value * 5.0 # Sensibilidad
    _perform_insert_movement(delta)

def _perform_insert_from_nudge(direction):
    """Maneja el ajuste frame a frame para la herramienta Insert."""
    _perform_insert_movement(float(direction))

def _perform_insert_movement(delta_frames):
    """Lógica central de movimiento para la herramienta Insert."""
    context = state.control_state.get('insert_context')
    sequencer = bpy.context.scene.sequence_editor
    if not context or not sequencer: return

    insert_strip = sequencer.sequences_all.get(context['insert_strip_name'])
    right_side_strips = [sequencer.sequences_all.get(n) for n in context['right_side_names']]
    if not insert_strip or not all(right_side_strips): return

    # Lógica de Límite (Clamp)
    final_delta = delta_frames
    if delta_frames < 0: # Solo al crear overlap
        max_overlap = context['insert_duration']
        current_overlap = abs(context['accumulated_delta'])

        allowed_additional_overlap = max_overlap - current_overlap

        if abs(delta_frames) > allowed_additional_overlap:
            final_delta = -allowed_additional_overlap

    if abs(final_delta) < 0.001: return

    context['accumulated_delta'] += final_delta

    insert_strip_move = int(round(final_delta))
    right_strips_move = int(round(final_delta * 2))

    # Mover insert_strip (X)
    insert_strip.frame_start += insert_strip_move

    # Mover right_side_strips (2X)
    for strip in right_side_strips:
        strip.frame_start += right_strips_move

    # Feedback del Playhead
    if state.control_state.get('strip_nav_follow_active', False):
        target_frame = _get_visible_range(insert_strip)[0] - 1
        bpy.context.scene.frame_current = max(bpy.context.scene.frame_start, target_frame)


# --- FIN: Implementación de la Herramienta INSERT ---

def register():
    pass

def unregister():
    pass

def register_actions():
    state.jog_actions['ripple'] = perform_ripple_from_jog
    state.jog_actions['splice_trim'] = _perform_splice_trim_from_jog
    state.jog_actions['insert'] = _perform_insert_from_jog