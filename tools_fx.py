# tools_fx.py

import bpy
import math
from . import state
from . import osc_feedback
from . import adds

# --- Constantes de Sensibilidad ---
SPEED_FACTOR_SENSITIVITY_JOG = 0.2
SPEED_FACTOR_SENSITIVITY_NUDGE = 0.05
SPEED_STRETCH_SENSITIVITY_JOG = 4.0
SPEED_STRETCH_SENSITIVITY_NUDGE = 1.0
SPEED_FRAME_LENGTH_SENSITIVITY_JOG = 4.0
SPEED_FRAME_LENGTH_SENSITIVITY_NUDGE = 1.0
PRECISION_DIVISOR = 4.0
TRANSFORM_SENSITIVITY_JOG = 0.02
TRANSFORM_SENSITIVITY_NUDGE = 0.01
TRANSFORM_ROT_SENSITIVITY_JOG = 2.0
TRANSFORM_ROT_SENSITIVITY_NUDGE = 1.0

# --- Funciones Auxiliares ---

def _get_active_speed_strip():
    """Valida y devuelve el Speed Strip activo."""
    selected = bpy.context.selected_sequences
    if len(selected) != 1 or selected[0].type != 'SPEED':
        osc_feedback.send_action_feedback("E SEL")
        return None
    return selected[0]

def _send_speed_method_feedback(strip):
    """Envía el método de control de velocidad actual a la superficie."""
    if strip:

        osc_feedback.send("/sp_method_feedback", strip.speed_control)

def _init_multiply_recalc_state(strip):
    """Prepara el estado para el recálculo de duración en modo Multiply."""
    if not strip: return
    state.control_state['multiply_recalc_context'] = {
        'strip_name': strip.name,
        'initial_duration': strip.frame_final_duration,
        'last_recalc_factor': 1.0
    }

# --- Manejadores de Lógica Principal ---

def _perform_speed_from_jog(jog_value):
    """Manejador principal para el JOG que enruta al método activo."""
    strip = _get_active_speed_strip()
    if not strip: return

    method = strip.speed_control

    sensitivity = 1.0
    if method == 'MULTIPLY':
        sensitivity = SPEED_FACTOR_SENSITIVITY_JOG
    elif method == 'STRETCH':
        sensitivity = SPEED_STRETCH_SENSITIVITY_JOG
    else: # FRAME_NUMBER y LENGTH
        sensitivity = SPEED_FRAME_LENGTH_SENSITIVITY_JOG
    
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_DIVISOR
    
    delta = jog_value * sensitivity

    if method == 'STRETCH':
        if strip.input_1:
            new_duration = strip.input_1.frame_final_duration + delta

            strip.input_1.frame_final_duration = max(1, int(round(new_duration)))
    
    elif method == 'MULTIPLY':

        strip.speed_factor += delta
    
    elif method == 'FRAME_NUMBER':

        strip.speed_frame_number += delta
    
    elif method == 'LENGTH':
        new_length = strip.speed_length + delta

        strip.speed_length = max(1, int(round(new_length)))

    _auto_record_speed_param(strip)

def _perform_speed_from_plus_minus(direction):
    strip = _get_active_speed_strip()
    if not strip: return


    method = strip.speed_control
    
    sensitivity = 1.0
    if method == 'MULTIPLY': sensitivity = SPEED_MULTIPLY_SENSITIVITY_NUDGE
    elif method == 'STRETCH': sensitivity = SPEED_STRETCH_SENSITIVITY_NUDGE
    else: sensitivity = SPEED_FRAME_LENGTH_SENSITIVITY_NUDGE

    delta = direction * sensitivity

    if method == 'STRETCH':
        if strip.input_1:
            new_duration = strip.input_1.frame_final_duration + delta
            strip.input_1.frame_final_duration = max(1, int(round(new_duration)))
    elif method == 'MULTIPLY':

        strip.speed_factor += delta
    elif method == 'FRAME_NUMBER':

        strip.speed_frame_number += delta
    elif method == 'LENGTH':

        new_length = strip.speed_length + delta
        strip.speed_length = max(1, int(round(new_length)))
    
    _auto_record_speed_param(strip)

# --- Manejadores de Keyframing ---

def _get_active_speed_param_path(strip):

    method = strip.speed_control
    if method == 'STRETCH':
        return 'input_1.frame_final_duration' if strip.input_1 else None
    elif method == 'MULTIPLY':
        return 'speed_factor'
    elif method == 'FRAME_NUMBER':
        return 'speed_frame_number'
    elif method == 'LENGTH':
        return 'speed_length'
    return None

def _auto_record_speed_param(strip):
    if not state.control_state.get('auto_record', False): return
    data_path = _get_active_speed_param_path(strip)
    if not data_path: return
    
    target = strip
    if 'input_1' in data_path:
        target, data_path = strip.input_1, data_path.replace('input_1.', '')
    
    try:
        target.keyframe_insert(data_path=data_path, frame=bpy.context.scene.frame_current)
    except (TypeError, RuntimeError): pass

def handle_speed_keyframe(address, args):
    if not args or not args[0]: return
    strip = _get_active_speed_strip()
    if not strip: return

    data_path = _get_active_speed_param_path(strip)
    if not data_path: return
    target = strip
    if 'input_1' in data_path:
        target, data_path = strip.input_1, data_path.replace('input_1.', '')
    target.keyframe_insert(data_path=data_path, frame=bpy.context.scene.frame_current)

def handle_speed_delete_keyframe(address, args):
    if not args or not args[0]: return
    strip = _get_active_speed_strip()
    if not strip: return

    data_path = _get_active_speed_param_path(strip)
    if not data_path: return
    target = strip
    if 'input_1' in data_path:
        target, data_path = strip.input_1, data_path.replace('input_1.', '')
    try:
        target.keyframe_delete(data_path=data_path, frame=bpy.context.scene.frame_current)
    except RuntimeError: pass

# --- Manejadores de Comandos OSC ---

def handle_speed_method_cycle(address, args):
    if not args or not args[0]: return
    strip = _get_active_speed_strip()
    if not strip: return

    direction = 1 if address.endswith('next') else -1
    

    rna_prop = strip.bl_rna.properties['speed_control']
    methods = [item.identifier for item in rna_prop.enum_items]
    
    try:
        current_index = methods.index(strip.speed_control)
        new_index = (current_index + direction) % len(methods)
        strip.speed_control = methods[new_index]
        _send_speed_method_feedback(strip)
    except ValueError: pass

def handle_speed_method_sync(address, args):
    if not args or not args[0]: return
    strip = _get_active_speed_strip()
    _send_speed_method_feedback(strip)

def handle_recalculate_length(address, args):
    if not args or not args[0]: return
    strip = _get_active_speed_strip()

    if not strip or strip.speed_control != 'MULTIPLY' or not strip.input_1: 
        return


    try:
        if strip.animation_data.action.fcurves.find('speed_factor'):
            osc_feedback.send_action_feedback("E KEY")
            return
    except AttributeError:
        pass

    ctx = state.control_state.get('multiply_recalc_context')
    if not ctx or ctx.get('strip_name') != strip.name:
        _init_multiply_recalc_state(strip)
        ctx = state.control_state['multiply_recalc_context']

    last_factor = ctx['last_recalc_factor']
    current_factor = strip.speed_factor
    
    if abs(current_factor) < 0.001: return

    ratio = last_factor / current_factor
    
    source_strip = strip.input_1
    current_source_duration = source_strip.frame_final_duration
    
    new_source_duration = current_source_duration * ratio
    source_strip.frame_final_duration = max(1, int(round(new_source_duration)))

   

    ctx['last_recalc_factor'] = current_factor

def handle_interpolate_toggle(address, args):
    if not args or not args[0]: return
    strip = _get_active_speed_strip()
    if not strip: return
    

    strip.use_frame_interpolate = not strip.use_frame_interpolate
    if state.control_state.get('auto_record', False):
        try:
            strip.keyframe_insert(data_path='use_frame_interpolate', frame=bpy.context.scene.frame_current)
        except (TypeError, RuntimeError): pass

def handle_speed_tool_activation(address, args):
    if not args: return
    is_pressed = bool(args[0])
    tool_name = "speed_tool"
    if is_pressed:
        strip = _get_active_speed_strip()
        if not strip: return
        bpy.ops.ed.undo_push(message="OSC Speed Edit")
        _init_multiply_recalc_state(strip)
        state.control_state.setdefault('active_tools', set()).add(tool_name)
    else:
        state.control_state.setdefault('active_tools', set()).discard(tool_name)
    osc_feedback.send_active_tool_feedback()

def register():
    state.control_state.setdefault('multiply_recalc_context', {})

# =====================================================================
# == HERRAMIENTA MULTICAM FX
# =====================================================================

# --- Funciones Auxiliares para Multicam ---

def _get_multicam_under_playhead():
    """Encuentra el strip de tipo MULTICAM más alto debajo del cabezal."""
    playhead = bpy.context.scene.frame_current
    candidates = [
        s for s in bpy.context.scene.sequence_editor.sequences_all
        if s.type == 'MULTICAM' and s.frame_final_start <= playhead < s.frame_final_end
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.channel)

def _find_empty_channel_above(strip):
    """Busca el primer canal completamente vacío por encima de un strip dado."""
    sequencer = bpy.context.scene.sequence_editor
    if not sequencer: return strip.channel + 1
    
    used_channels = {s.channel for s in sequencer.sequences_all}
    channel = strip.channel + 1
    while True:
        if channel not in used_channels:
            return channel
        channel += 1


def _apply_multicam_alpha_fade(left_strip, right_strip):
    """
    Aplica keyframes de opacidad a dos strips de Multicam para crear un crossfade.
    La lógica es interna y no depende de otros módulos.
    """
    if not left_strip or not right_strip:
        return

    # Calcular el rango del solapamiento
    start_frame = right_strip.frame_final_start
    end_frame = left_strip.frame_final_end
    
    # La transición necesita al menos un fotograma intermedio para funcionar
    if end_frame - start_frame < 2:
        return

    # Asegurar que ambos strips tengan blend_alpha
    if not hasattr(left_strip, 'blend_alpha') or not hasattr(right_strip, 'blend_alpha'):
        return
    
    # --- Animación del strip izquierdo (Fade Out) ---
    left_strip.keyframe_insert(data_path='blend_alpha', frame=start_frame)
    left_strip.blend_alpha = 0.0
    left_strip.keyframe_insert(data_path='blend_alpha', frame=end_frame - 1)
    
    # --- Animación del strip derecho (Fade In) ---
    right_strip.blend_alpha = 0.0
    right_strip.keyframe_insert(data_path='blend_alpha', frame=start_frame)
    right_strip.blend_alpha = 1.0
    right_strip.keyframe_insert(data_path='blend_alpha', frame=end_frame - 1)
    
    # --- Ajustar Interpolación a LINEAL ---
    for strip in [left_strip, right_strip]:
        try:
            if strip.animation_data and strip.animation_data.action:
                fcurve = strip.animation_data.action.fcurves.find('blend_alpha')
                if fcurve:
                    for kp in fcurve.keyframe_points:
                        if math.isclose(kp.co.x, start_frame) or math.isclose(kp.co.x, end_frame - 1):
                            kp.interpolation = 'LINEAR'
                    fcurve.update()
        except Exception:
            pass # Falla silenciosamente si hay problemas con los fcurves

def _clear_multicam_alpha_fade(strips):
    """Limpia los keyframes de blend_alpha de una lista de strips."""
    for strip in strips:
        if not strip or not hasattr(strip, 'blend_alpha'):
            continue
        
        strip.blend_alpha = 1.0
        try:
            if strip.animation_data and strip.animation_data.action:
                fcurve = strip.animation_data.action.fcurves.find('blend_alpha')
                if fcurve:
                    strip.animation_data.action.fcurves.remove(fcurve)
        except Exception:
            pass # Falla silenciosamente

# --- Manejadores de Lógica Principal de Multicam ---

def _perform_multicam_from_jog(jog_value):
    """Mueve el punto de corte del multicam con el jog."""
    delta = jog_value * 5.0 
    _perform_multicam_interactive_move(delta)

def _perform_multicam_from_plus_minus(direction):
    """Mueve el punto de corte del multicam con Pstrip/Nstrip."""
    _perform_multicam_interactive_move(float(direction))

def _perform_multicam_interactive_move(delta_frames):
    """Lógica central de movimiento para el ajuste interactivo del corte."""
    context = state.control_state.get('multicam_context')
    if not context: return

    selected = bpy.context.selected_sequences
    if not selected or len(selected) != 1: return
    new_strip = selected[0]
    
    original_strip_name = context.get('original_strip_name')
    if not original_strip_name: return
    
    original_strip = bpy.context.scene.sequence_editor.sequences_all.get(original_strip_name)
    if not original_strip: return

    final_delta = int(round(delta_frames))
    if final_delta == 0: return

    potential_new_start = new_strip.frame_start + final_delta
    is_overlap_imminent = potential_new_start < original_strip.frame_final_end
    moved_flag = context.get('moved_to_safe_channel', False)

    if is_overlap_imminent and not moved_flag:
        safe_channel = _find_empty_channel_above(new_strip)
        new_strip.channel = safe_channel
        context['moved_to_safe_channel'] = True

    new_strip.frame_start += final_delta

# --- Manejadores de Comandos OSC de Multicam ---

def handle_multicam_cut_mode_toggle(address, args):
    """Activa/desactiva el modo de corte para la herramienta multicam."""
    if not args: return
    new_state = bool(args[0])
    state.control_state['multicam_cut_mode'] = new_state
    osc_feedback.send_action_feedback("CUT MODE ON" if new_state else "CUT MODE OFF")

def handle_multicam_command(address, args):
    """Manejador principal para los comandos /multicam/N."""
    if not args: return
    
    try:
        camera_index = int(address.split('/')[-1])
    except (ValueError, IndexError):
        return

    is_pressed = bool(args[0])
    
    if not state.control_state.get('multicam_cut_mode', False):
        if is_pressed:
            strip = _get_multicam_under_playhead() or (bpy.context.selected_sequences[0] if bpy.context.selected_sequences and bpy.context.selected_sequences[0].type == 'MULTICAM' else None)
            if strip:
                strip.multicam_source = camera_index
        return

    tool_name = "multicam_tool"
    if is_pressed:
        bpy.ops.sequencer.select_all(action='DESELECT')
        original_strip = _get_multicam_under_playhead()
        if not original_strip:
            osc_feedback.send_action_feedback("E NO MULTICAM")
            return
        
        original_strip.select = True
        bpy.context.scene.sequence_editor.active_strip = original_strip
        
        original_strip_name = original_strip.name
        names_before_cut = {s.name for s in bpy.context.scene.sequence_editor.sequences_all}
        
        state.control_state.setdefault('active_tools', set()).add(tool_name)
        osc_feedback.send_active_tool_feedback()

        ctx_override = adds.get_sequencer_context()
        if not ctx_override: return
        with bpy.context.temp_override(**ctx_override):
             bpy.ops.sequencer.split(side='RIGHT', frame=bpy.context.scene.frame_current)
        
        new_strip_name_set = {s.name for s in bpy.context.scene.sequence_editor.sequences_all} - names_before_cut
        if not new_strip_name_set: return
        new_strip_name = new_strip_name_set.pop()
        new_strip = bpy.context.scene.sequence_editor.sequences_all.get(new_strip_name)
        
        if not new_strip: return
        
        new_strip.multicam_source = camera_index
        
        state.control_state['multicam_context'] = {
            'original_strip_name': original_strip_name,
            'moved_to_safe_channel': False
        }

    else:
        context = state.control_state.get('multicam_context')
        if not context: return
        
        original_strip = bpy.context.scene.sequence_editor.sequences_all.get(context.get('original_strip_name'))
        new_strip = bpy.context.selected_sequences[0] if bpy.context.selected_sequences else None

        if original_strip and new_strip:
            overlap_start = new_strip.frame_final_start
            overlap_end = original_strip.frame_final_end
            overlap_duration = overlap_end - overlap_start

            if overlap_duration > 1:
                _apply_multicam_alpha_fade(original_strip, new_strip)
            else:
                _clear_multicam_alpha_fade([original_strip, new_strip])

        state.control_state.setdefault('active_tools', set()).discard(tool_name)
        state.control_state['multicam_context'] = {}
        osc_feedback.send_active_tool_feedback()

def register_multicam_actions():
    state.jog_actions['multicam_tool'] = _perform_multicam_from_jog
    state.plus_minus_actions['multicam_tool'] = _perform_multicam_from_plus_minus

# =====================================================================
# == HERRAMIENTA WIPE FX
# =====================================================================

# --- Constantes de Sensibilidad para Wipe ---
WIPE_SENSITIVITY_JOG = 0.05
WIPE_SENSITIVITY_NUDGE = 0.02
WIPE_ANGLE_SENSITIVITY_JOG = 2.0
WIPE_ANGLE_SENSITIVITY_NUDGE = 1.0

# --- Funciones Auxiliares para Wipe ---

def _get_active_wipe_strip():
    """Valida y devuelve el Wipe Strip activo."""
    selected = bpy.context.selected_sequences
    if len(selected) != 1 or selected[0].type != 'WIPE':
        osc_feedback.send_action_feedback("E SEL")
        return None
    return selected[0]

def _send_wipe_type_feedback(strip):
    """Envía el tipo de Wipe actual a la superficie."""
    if strip:
        osc_feedback.send("/wipe_type_feedback", strip.transition_type)

# --- Manejadores de Lógica Principal de Wipe ---

def _perform_wipe_from_jog(jog_value):
    strip = _get_active_wipe_strip()
    if not strip: return

    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection({"wipe_blur", "wipe_angle", "wipe_fader"})), None)
    if not active_tool: return

    sensitivity = WIPE_SENSITIVITY_JOG
    if active_tool == "wipe_angle":
        sensitivity = WIPE_ANGLE_SENSITIVITY_JOG
    
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_DIVISOR
    
    delta = jog_value * sensitivity

    if active_tool == "wipe_blur":
        strip.blur_width = max(0, strip.blur_width + delta)
    elif active_tool == "wipe_angle":
        strip.angle += math.radians(delta)
    elif active_tool == "wipe_fader":
        try:
            strip.effect_fader = max(0.0, min(1.0, strip.effect_fader + delta))
        except AttributeError:
            # Falla silenciosamente si el parámetro es de solo lectura
            pass
    
    _auto_record_wipe_param(strip, active_tool)

def _perform_wipe_from_plus_minus(direction):
    strip = _get_active_wipe_strip()
    if not strip: return

    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection({"wipe_blur", "wipe_angle", "wipe_fader"})), None)
    if not active_tool: return

    sensitivity = WIPE_SENSITIVITY_NUDGE
    if active_tool == "wipe_angle":
        sensitivity = WIPE_ANGLE_SENSITIVITY_NUDGE

    delta = direction * sensitivity

    if active_tool == "wipe_blur":
        strip.blur_width = max(0, strip.blur_width + delta)
    elif active_tool == "wipe_angle":
        strip.angle += math.radians(delta)
    elif active_tool == "wipe_fader":
        try:
            strip.effect_fader = max(0.0, min(1.0, strip.effect_fader + delta))
        except AttributeError:
            pass # Falla silenciosamente

    _auto_record_wipe_param(strip, active_tool)

# --- Manejadores de Keyframing de Wipe ---

def _get_active_wipe_param_path(active_tool):
    """Devuelve el data_path del parámetro de la herramienta Wipe activa."""
    if active_tool == "wipe_blur": return "blur_width"
    if active_tool == "wipe_angle": return "angle"
    if active_tool == "wipe_fader": return "effect_fader"
    return None

def _auto_record_wipe_param(strip, active_tool):
    if not state.control_state.get('auto_record', False): return
    data_path = _get_active_wipe_param_path(active_tool)
    if not data_path: return
    try:
        strip.keyframe_insert(data_path=data_path, frame=bpy.context.scene.frame_current)
    except (TypeError, RuntimeError): pass

def handle_wipe_keyframe(address, args):
    """Inserta un keyframe en el parámetro de la herramienta Wipe activa."""
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    if not strip: return
    
    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection({"wipe_blur", "wipe_angle", "wipe_fader"})), None)
    data_path = _get_active_wipe_param_path(active_tool)
    if data_path:
        strip.keyframe_insert(data_path=data_path, frame=bpy.context.scene.frame_current)

def handle_wipe_delete_keyframe(address, args):
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    if not strip: return
    
    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection({"wipe_blur", "wipe_angle", "wipe_fader"})), None)
    data_path = _get_active_wipe_param_path(active_tool)
    if data_path:
        try:
            strip.keyframe_delete(data_path=data_path, frame=bpy.context.scene.frame_current)
        except RuntimeError: pass

# --- Manejadores de Comandos OSC de Wipe ---

def handle_wipe_type_cycle(address, args):
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    if not strip: return
    
    direction = 1 if address.endswith('next') else -1
    rna_prop = strip.bl_rna.properties['transition_type']
    types = [item.identifier for item in rna_prop.enum_items]
    try:
        current_index = types.index(strip.transition_type)
        new_index = (current_index + direction) % len(types)
        strip.transition_type = types[new_index]
        _send_wipe_type_feedback(strip)
    except ValueError: pass

def handle_wipe_type_sync(address, args):
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    _send_wipe_type_feedback(strip)

def handle_wipe_type_keyframe(address, args):
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    if strip:
        strip.keyframe_insert(data_path='transition_type', frame=bpy.context.scene.frame_current)

def handle_wipe_direction_toggle(address, args):
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    if strip:
        strip.direction = 'OUT' if strip.direction == 'IN' else 'IN'
        if state.control_state.get('auto_record', False):
            strip.keyframe_insert(data_path='direction', frame=bpy.context.scene.frame_current)

def handle_wipe_default_fade_toggle(address, args):
    if not args or not args[0]: return
    strip = _get_active_wipe_strip()
    if strip:
        strip.use_default_fade = not strip.use_default_fade
        if state.control_state.get('auto_record', False):
            strip.keyframe_insert(data_path='use_default_fade', frame=bpy.context.scene.frame_current)

def handle_wipe_tool_activation(address, args):
    if not args: return
    is_pressed = bool(args[0])
    tool_name = address.strip('/').split('/')[-1] # "wipe_blur", "wipe_angle", etc.
    
    if is_pressed:
        if not _get_active_wipe_strip(): return
        bpy.ops.ed.undo_push(message=f"OSC Edit {tool_name}")
        state.control_state.setdefault('active_tools', set()).add(tool_name)
    else:
        state.control_state.setdefault('active_tools', set()).discard(tool_name)
    
    osc_feedback.send_active_tool_feedback()

def register_wipe_actions():
    wipe_tools = ["wipe_blur", "wipe_angle", "wipe_fader"]
    for tool in wipe_tools:
        state.jog_actions[tool] = _perform_wipe_from_jog
        state.plus_minus_actions[tool] = _perform_wipe_from_plus_minus
        state.tool_specific_actions[tool] = {
            '/key': handle_wipe_keyframe,
            '/del': handle_wipe_delete_keyframe,
        }

# =====================================================================
# == HERRAMIENTAS BLUR, GLOW, CROSS
# =====================================================================

# --- Constantes de Sensibilidad ---
GENERIC_FX_SENSITIVITY_JOG = 0.05
GENERIC_FX_SENSITIVITY_NUDGE = 0.02

# --- Diccionario de Propiedades de Herramientas ---
# Mapea el nombre de la herramienta interna a la propiedad de Blender y su tipo
FX_TOOL_PROPERTIES = {
    # Cross
    "cross_fader":    {'prop': 'effect_fader', 'type': 'float', 'strip': 'CROSS'},
    # Blur
    "blur_x":         {'prop': 'size_x', 'type': 'float', 'strip': 'GAUSSIAN_BLUR'},
    "blur_y":         {'prop': 'size_y', 'type': 'float', 'strip': 'GAUSSIAN_BLUR'},
    # Glow
    "glow_threshold": {'prop': 'threshold', 'type': 'float', 'strip': 'GLOW'},
    "glow_clamp":     {'prop': 'clamp', 'type': 'float', 'strip': 'GLOW'},
    "glow_boost":     {'prop': 'boost_factor', 'type': 'float', 'strip': 'GLOW'},
    "glow_blur":      {'prop': 'blur_radius', 'type': 'float', 'strip': 'GLOW'},
    "glow_quality":   {'prop': 'quality', 'type': 'int', 'strip': 'GLOW'},
    # Transform
    "transf_pos_x":   {'prop': 'translate_start_x', 'strip': 'TRANSFORM', 'type': 'float', 'sens_jog': TRANSFORM_SENSITIVITY_JOG, 'sens_nudge': TRANSFORM_SENSITIVITY_NUDGE},
    "transf_pos_y":   {'prop': 'translate_start_y', 'strip': 'TRANSFORM', 'type': 'float', 'sens_jog': TRANSFORM_SENSITIVITY_JOG, 'sens_nudge': TRANSFORM_SENSITIVITY_NUDGE},
    "transf_scale_x": {'prop': 'scale_start_x', 'strip': 'TRANSFORM', 'type': 'float', 'sens_jog': TRANSFORM_SENSITIVITY_JOG, 'sens_nudge': TRANSFORM_SENSITIVITY_NUDGE},
    "transf_scale_y": {'prop': 'scale_start_y', 'strip': 'TRANSFORM', 'type': 'float', 'sens_jog': TRANSFORM_SENSITIVITY_JOG, 'sens_nudge': TRANSFORM_SENSITIVITY_NUDGE},
    "transf_rot":     {'prop': 'rotation_start', 'strip': 'TRANSFORM', 'type': 'float', 'sens_jog': TRANSFORM_ROT_SENSITIVITY_JOG, 'sens_nudge': TRANSFORM_ROT_SENSITIVITY_NUDGE, 'is_degrees': True},
    "transf_uniform_scale": {'prop': 'use_uniform_scale', 'strip': 'TRANSFORM', 'type': 'bool'},

}

# --- Funciones Auxiliares Genéricas ---

def _get_active_fx_strip(strip_type):
    """Valida y devuelve un strip de efecto del tipo especificado."""
    selected = bpy.context.selected_sequences
    if len(selected) != 1 or selected[0].type != strip_type:
        osc_feedback.send_action_feedback("E SEL")
        return None
    return selected[0]

# --- Manejadores de Lógica Principal Genéricos ---

def _perform_fx_from_jog(jog_value):
    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection(FX_TOOL_PROPERTIES.keys())), None)
    # Ignorar el jog para herramientas de tipo booleano
    if not active_tool or FX_TOOL_PROPERTIES[active_tool]['type'] == 'bool': 
        return

    details = FX_TOOL_PROPERTIES[active_tool]
    strip = _get_active_fx_strip(details['strip'])
    if not strip: return

    sensitivity = details.get('sens_jog', GENERIC_FX_SENSITIVITY_JOG)
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_DIVISOR
    delta = jog_value * sensitivity

    if details.get('is_degrees', False):
        delta = math.radians(delta)

    current_val = getattr(strip, details['prop'])
    new_val = current_val + delta
    
    if details['type'] == 'int': new_val = max(0, int(round(new_val)))
    elif details['prop'] != 'translate_start_x' and details['prop'] != 'translate_start_y':
        new_val = max(0.0, new_val)

    setattr(strip, details['prop'], new_val)
    _auto_record_fx_param(strip, active_tool)

def _perform_fx_from_plus_minus(direction):
    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection(FX_TOOL_PROPERTIES.keys())), None)
    if not active_tool: return

    details = FX_TOOL_PROPERTIES[active_tool]
    strip = _get_active_fx_strip(details['strip'])
    if not strip: return

    # Lógica especial para la herramienta de toggle booleano
    if details['type'] == 'bool':
        current_val = getattr(strip, details['prop'])
        setattr(strip, details['prop'], not current_val)
        _auto_record_fx_param(strip, active_tool)
        return

    sensitivity = details.get('sens_nudge', GENERIC_FX_SENSITIVITY_NUDGE)
    delta = direction * sensitivity

    if details.get('is_degrees', False):
        delta = math.radians(delta)

    current_val = getattr(strip, details['prop'])
    new_val = current_val + delta

    if details['type'] == 'int': new_val = max(0, int(round(new_val)))
    elif details['prop'] != 'translate_start_x' and details['prop'] != 'translate_start_y':
        new_val = max(0.0, new_val)

    setattr(strip, details['prop'], new_val)
    _auto_record_fx_param(strip, active_tool)

# --- Manejadores de Keyframing Genéricos ---

def _auto_record_fx_param(strip, active_tool):
    if not state.control_state.get('auto_record', False): return
    details = FX_TOOL_PROPERTIES.get(active_tool)
    if not details: return
    try:
        strip.keyframe_insert(data_path=details['prop'], frame=bpy.context.scene.frame_current)
    except (TypeError, RuntimeError): pass

def handle_fx_keyframe(address, args):
    if not args or not args[0]: return
    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection(FX_TOOL_PROPERTIES.keys())), None)
    if not active_tool: return
    
    details = FX_TOOL_PROPERTIES[active_tool]
    strip = _get_active_fx_strip(details['strip'])
    if strip:
        strip.keyframe_insert(data_path=details['prop'], frame=bpy.context.scene.frame_current)

def handle_fx_delete_keyframe(address, args):
    if not args or not args[0]: return
    active_tool = next(iter(state.control_state.get('active_tools', set()).intersection(FX_TOOL_PROPERTIES.keys())), None)
    if not active_tool: return

    details = FX_TOOL_PROPERTIES[active_tool]
    strip = _get_active_fx_strip(details['strip'])
    if strip:
        try:
            strip.keyframe_delete(data_path=details['prop'], frame=bpy.context.scene.frame_current)
        except RuntimeError: pass

# --- Manejadores de Comandos OSC ---

def handle_fx_tool_activation(address, args):
    """Manejador genérico para activar herramientas de FX."""
    if not args: return
    is_pressed = bool(args[0])
    tool_name = address.strip('/').split('/')[-1]

    if tool_name not in FX_TOOL_PROPERTIES: return
    
    details = FX_TOOL_PROPERTIES[tool_name]
    
    # Limpiar otras herramientas activas del mismo grupo antes de activar una nueva
    active_tools = state.control_state.setdefault('active_tools', set())
    if is_pressed:
        if not _get_active_fx_strip(details['strip']): return
        
        # Desactiva otras herramientas de FX para evitar conflictos
        active_tools.difference_update(FX_TOOL_PROPERTIES.keys())
        
        bpy.ops.ed.undo_push(message=f"OSC Edit {tool_name}")
        active_tools.add(tool_name)
    else:
        active_tools.discard(tool_name)
    
    osc_feedback.send_active_tool_feedback()

# --- Toggles de Acción Directa (sin keyframes) ---

def handle_cross_default_fade_toggle(address, args):
    if not args or not args[0]: return
    strip = _get_active_fx_strip('CROSS')
    if strip:
        strip.use_default_fade = not strip.use_default_fade

def handle_glow_only_boost_toggle(address, args):
    if not args or not args[0]: return
    strip = _get_active_fx_strip('GLOW')
    if strip:
        strip.use_only_boost = not strip.use_only_boost


def handle_transform_interpolation_cycle(address, args):
    if not args or not args[0]: return
    strip = _get_active_fx_strip('TRANSFORM')
    if not strip: return
    try:
        current_index = TRANSFORM_INTERPOLATION_ORDER.index(strip.interpolation)
        new_index = (current_index + 1) % len(TRANSFORM_INTERPOLATION_ORDER)
        strip.interpolation = TRANSFORM_INTERPOLATION_ORDER[new_index]
        osc_feedback.send("/transf_inter_feedback", strip.interpolation)
    except ValueError: pass

def handle_transform_interpolation_sync(address, args):
    if not args or not args[0]: return
    strip = _get_active_fx_strip('TRANSFORM')
    if strip:
        osc_feedback.send("/transf_inter_feedback", strip.interpolation)

def handle_transform_unit_toggle(address, args):
    if not args or not args[0]: return
    strip = _get_active_fx_strip('TRANSFORM')
    if not strip: return
    try:
        current_index = TRANSFORM_UNIT_ORDER.index(strip.translation_unit)
        new_index = (current_index + 1) % len(TRANSFORM_UNIT_ORDER)
        strip.translation_unit = TRANSFORM_UNIT_ORDER[new_index]
        osc_feedback.send("/transf_unit_feedback", strip.translation_unit)
    except ValueError: pass

def handle_transform_unit_sync(address, args):
    if not args or not args[0]: return
    strip = _get_active_fx_strip('TRANSFORM')
    if strip:
        osc_feedback.send("/transf_unit_feedback", strip.translation_unit)

def register_transform_actions():
    # El registro de estas herramientas ya está cubierto por el bucle genérico
    # en register_fx_actions(), por lo que esta función está vacía,
    # pero la mantenemos por consistencia estructural.
    pass

def register_fx_actions():
    """Registra acciones para herramientas genéricas de FX (Cross, Blur, Glow, Transform)."""
    for tool_name in FX_TOOL_PROPERTIES:
        state.jog_actions[tool_name] = _perform_fx_from_jog
        state.plus_minus_actions[tool_name] = _perform_fx_from_plus_minus
        state.tool_specific_actions[tool_name] = {
            '/key': handle_fx_keyframe,
            '/del': handle_fx_delete_keyframe,
        }

def register_actions():
    """Registra todas las acciones de este módulo."""
    # Speed Tool
    state.jog_actions['speed_tool'] = _perform_speed_from_jog
    state.plus_minus_actions['speed_tool'] = _perform_speed_from_plus_minus
    state.tool_specific_actions['speed_tool'] = {
        '/key': handle_speed_keyframe,
        '/del': handle_speed_delete_keyframe,
    }
    
    # Registro de las demás herramientas
    register_multicam_actions()
    register_wipe_actions()
    register_fx_actions()
    register_transform_actions()

    
def unregister():
    pass