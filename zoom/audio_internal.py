# audio_internal.py

import bpy
import math
from . import state
from . import osc_feedback

# --- Constantes de Sensibilidad ---
PLUS_MINUS_SENSITIVITY_VOLUME = 0.02
JOG_SENSITIVITY_VOLUME = 0.05
PLUS_MINUS_SENSITIVITY_PAN = 0.05
JOG_SENSITIVITY_PAN = 0.1
PRECISION_MODE_DIVISOR = 4.0

# --- Parámetros de Snap ---
# El umbral para que el valor "salte" al valor por defecto
SNAP_THRESHOLD_VOLUME = 0.05  # Se activa si el valor está entre 0.95 y 1.05
SNAP_THRESHOLD_PAN = 0.1     # Se activa si el valor está entre -0.1 y 0.1 (para centrar)

# --- Diccionario de Herramientas de Audio ---
AUDIO_TOOL_PROPERTIES = {
    'volume': {
        'prop': 'volume',
        'sens_pm': PLUS_MINUS_SENSITIVITY_VOLUME,
        'sens_jog': JOG_SENSITIVITY_VOLUME,
        'snap_threshold': SNAP_THRESHOLD_VOLUME,
        'snap_default': 1.0
    },
    'pan': {
        'prop': 'pan',
        'sens_pm': PLUS_MINUS_SENSITIVITY_PAN,
        'sens_jog': JOG_SENSITIVITY_PAN,
        'snap_threshold': SNAP_THRESHOLD_PAN,
        'snap_default': 0.0
    },
}

# --- Funciones Auxiliares ---

def _get_selected_audio_strips():
    """Devuelve una lista de los strips de audio y escena seleccionados."""
    compatible_types = {'SOUND', 'SCENE'}
    return [s for s in bpy.context.selected_sequences if s.type in compatible_types]

def _tag_vse_redraw():
    """Fuerza el redibujado del área del VSE para mostrar cambios como nuevos keyframes."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()

def _auto_record_insert_key(target, data_path):
    """Inserta un keyframe si el auto-record está activo."""
    if not state.control_state.get('auto_record', False):
        return
    frame = bpy.context.scene.frame_current
    try:
        target.keyframe_insert(data_path=data_path, frame=frame, options={'INSERTKEY_NEEDED'})
    except (TypeError, RuntimeError):
        pass

# --- Lógica Central de Modificación ---

def _perform_property_change(tool_name, delta):
    """
    Función genérica para modificar una propiedad de audio, con lógica de snap opcional.
    """
    strips = _get_selected_audio_strips()
    if not strips: return

    details = AUDIO_TOOL_PROPERTIES[tool_name]
    prop_name = details['prop']
    use_snap = state.control_state.get('audio_snap_active', False)
    snap_threshold = details['snap_threshold']
    snap_default = details['snap_default']

    for strip in strips:

        if tool_name == 'pan':

            # Comprobamos que el strip sea de tipo SOUND y tenga un bloque de sonido asignado
            if strip.type == 'SOUND' and strip.sound:
                if strip.sound.use_mono:
                    strip.sound.use_mono = True
                    _auto_record_insert_key(strip.sound, 'use_mono')


        current_val = getattr(strip, prop_name)
        new_val = current_val + delta

        # Lógica de Snap al valor por defecto
        if use_snap:
            if abs(current_val - snap_default) > snap_threshold and abs(new_val - snap_default) <= snap_threshold:
                new_val = snap_default

        # Limitar paneo a su rango válido (-1.0 a 1.0)
        if tool_name == 'pan':
            new_val = max(-1.0, min(1.0, new_val))

        setattr(strip, prop_name, new_val)
        _auto_record_insert_key(strip, prop_name)

    final_value = getattr(strips[0], prop_name)
    osc_feedback.send_active_tool_value_feedback(final_value)

# --- Manejadores para Jog y Plus/Minus ---

def _perform_audio_tool_from_plus_minus(direction):
    active_tools = state.control_state.get('active_tools', set())
    if not active_tools: return
    tool_name = next(iter(active_tools))

    if tool_name not in AUDIO_TOOL_PROPERTIES: return
    details = AUDIO_TOOL_PROPERTIES[tool_name]

    sensitivity = details['sens_pm']
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_MODE_DIVISOR

    delta = direction * sensitivity
    _perform_property_change(tool_name, delta)


def _perform_audio_tool_from_jog(jog_value):
    active_tools = state.control_state.get('active_tools', set())
    if not active_tools: return
    tool_name = next(iter(active_tools))

    if tool_name not in AUDIO_TOOL_PROPERTIES: return
    details = AUDIO_TOOL_PROPERTIES[tool_name]

    sensitivity = details['sens_jog']
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_MODE_DIVISOR

    delta = jog_value * sensitivity
    _perform_property_change(tool_name, delta)


# --- Manejadores de Keyframes ---

def _handle_audio_keyframe(address, args, prop_name):
    if not args or not args[0]: return
    strips = _get_selected_audio_strips()
    if not strips: return
    
    frame = bpy.context.scene.frame_current
    for strip in strips:
        strip.keyframe_insert(data_path=prop_name, frame=frame)
    _tag_vse_redraw()

def _handle_audio_delete_keyframe(address, args, prop_name):
    if not args or not args[0]: return
    strips = _get_selected_audio_strips()
    if not strips: return

    frame = bpy.context.scene.frame_current
    for strip in strips:
        try:
            strip.keyframe_delete(data_path=prop_name, frame=frame)
        except RuntimeError:
            pass
    _tag_vse_redraw()

# --- Manejadores de Comandos OSC ---

def handle_tool_activation(address, args):
    """Activa/desactiva una herramienta de audio y envía feedback."""
    if not args: return
    is_pressed = bool(args[0])

    tool_name = address.replace('/audio_', '').strip('/')

    if is_pressed:
        if not _get_selected_audio_strips():
            print(f"OSC Audio: No hay strips de audio/escena seleccionados para la herramienta '{tool_name}'.")
            return
        
        bpy.ops.ed.undo_push(message=f"OSC Tool: {tool_name}")
        state.control_state['active_tools'].add(tool_name)
        osc_feedback.send_active_tool_feedback()

        prop_name = AUDIO_TOOL_PROPERTIES[tool_name]['prop']
        initial_val = getattr(_get_selected_audio_strips()[0], prop_name)
        osc_feedback.send_active_tool_value_feedback(initial_val)
    else:
        state.control_state['active_tools'].discard(tool_name)
        osc_feedback.send_active_tool_feedback()

def handle_audio_snap_toggle(address, args):
    """Activa o desactiva el modo de snap para las herramientas de audio."""
    if not args or not isinstance(args[0], bool): return
    new_state = args[0]
    state.control_state['audio_snap_active'] = new_state
    print(f"OSC Audio: Snap al valor por defecto {'ACTIVADO' if new_state else 'DESACTIVADO'}")
    osc_feedback.send("/audio_snap/state", 1 if new_state else 0)


# --- Registro de Acciones ---

def register_actions():
    """Registra las acciones de este módulo en el estado global."""
    
    # Volumen
    state.jog_actions['volume'] = _perform_audio_tool_from_jog
    state.plus_minus_actions['volume'] = _perform_audio_tool_from_plus_minus
    state.tool_specific_actions['volume'] = {
        '/key': lambda a, r: _handle_audio_keyframe(a, r, 'volume'),
        '/del': lambda a, r: _handle_audio_delete_keyframe(a, r, 'volume'),
    }

    # Pan
    state.jog_actions['pan'] = _perform_audio_tool_from_jog
    state.plus_minus_actions['pan'] = _perform_audio_tool_from_plus_minus
    state.tool_specific_actions['pan'] = {
        '/key': lambda a, r: _handle_audio_keyframe(a, r, 'pan'),
        '/del': lambda a, r: _handle_audio_delete_keyframe(a, r, 'pan'),
    }

def register():
    pass

def unregister():
    pass