# bl_cam_optics.py

import bpy
import math
from . import state
from . import osc_feedback
from . import bl_cam

# --- Constantes de Sensibilidad ---
JOG_SENSITIVITY_LENS = 15.0
PLUS_MINUS_SENSITIVITY_LENS = 1.0
JOG_SENSITIVITY_FOCUS = 0.5
PLUS_MINUS_SENSITIVITY_FOCUS = 0.05
JOG_SENSITIVITY_SHIFT = 0.05
PLUS_MINUS_SENSITIVITY_SHIFT = 0.01
JOG_SENSITIVITY_FSTOP = 0.5
PLUS_MINUS_SENSITIVITY_FSTOP = 0.1
JOG_SENSITIVITY_BLADES = 1.0
PLUS_MINUS_SENSITIVITY_BLADES = 1
JOG_SENSITIVITY_ROTATION = 15.0      # Grados
PLUS_MINUS_SENSITIVITY_ROTATION = 2.0 # Grados
JOG_SENSITIVITY_RATIO = 0.1
PLUS_MINUS_SENSITIVITY_RATIO = 0.02
PRECISION_DIVISOR = 4.0

# --- Diccionario de Herramientas ---
OPTICS_TOOL_PROPERTIES = {
    'focal_length': {'prop': 'lens', 'sens_jog': JOG_SENSITIVITY_LENS, 'sens_pm': PLUS_MINUS_SENSITIVITY_LENS, 'min': 1.0},
    'shift_x':      {'prop': 'shift_x', 'sens_jog': JOG_SENSITIVITY_SHIFT, 'sens_pm': PLUS_MINUS_SENSITIVITY_SHIFT},
    'shift_y':      {'prop': 'shift_y', 'sens_jog': JOG_SENSITIVITY_SHIFT, 'sens_pm': PLUS_MINUS_SENSITIVITY_SHIFT},
    'dof_distance': {'prop': 'dof.focus_distance', 'sens_jog': JOG_SENSITIVITY_FOCUS, 'sens_pm': PLUS_MINUS_SENSITIVITY_FOCUS, 'min': 0.0},
    'fstop':        {'prop': 'dof.aperture_fstop', 'sens_jog': JOG_SENSITIVITY_FSTOP, 'sens_pm': PLUS_MINUS_SENSITIVITY_FSTOP, 'min': 0.01},
    'dia_blades':   {'prop': 'dof.aperture_blades', 'sens_jog': JOG_SENSITIVITY_BLADES, 'sens_pm': PLUS_MINUS_SENSITIVITY_BLADES, 'min': 3, 'type': 'int'},
    'dia_rot':      {'prop': 'dof.aperture_rotation', 'sens_jog': JOG_SENSITIVITY_ROTATION, 'sens_pm': PLUS_MINUS_SENSITIVITY_ROTATION, 'type': 'rad'},
    'dist_ratio':   {'prop': 'dof.aperture_ratio', 'sens_jog': JOG_SENSITIVITY_RATIO, 'sens_pm': PLUS_MINUS_SENSITIVITY_RATIO, 'min': 0.01},
}

# --- Funciones Auxiliares ---

def _get_active_cameras():
    """Obtiene las cámaras activas y las "despierta" en el depsgraph."""
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return []
    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        for cam in cams:
            _ = cam.evaluated_get(depsgraph)
    except Exception:
        pass
    return cams

def _force_vse_refresh():
    """El "truco de mendruco" para invalidar el caché del VSE."""
    if bpy.context.scene and bpy.context.scene.sequence_editor:
        for strip in bpy.context.selected_sequences:
            if strip.type == 'SCENE':
                strip.mute = True
                strip.mute = False

def _get_nested_attr(obj, attr_path):
    """Obtiene un atributo anidado (ej: 'dof.aperture_fstop')."""
    keys = attr_path.split('.')
    for key in keys[:-1]:
        obj = getattr(obj, key, None)
        if obj is None: return None
    return getattr(obj, keys[-1], None)

def _set_nested_attr(obj, attr_path, value):
    """Establece un atributo anidado."""
    keys = attr_path.split('.')
    for key in keys[:-1]:
        obj = getattr(obj, key)
    setattr(obj, keys[-1], value)

def _auto_keyframe_if_needed(data_block, property_path):
    """Inserta un keyframe si auto-record está activo."""
    if state.control_state.get('auto_record', False):
        try:
            data_block.keyframe_insert(data_path=property_path, frame=bpy.context.scene.frame_current)
        except (TypeError, RuntimeError):
            pass

# --- Lógica Central ---

def _apply_property_delta(tool_name, delta):
    """Aplica un cambio a una propiedad de óptica y envía feedback."""
    if tool_name not in OPTICS_TOOL_PROPERTIES: return

    details = OPTICS_TOOL_PROPERTIES[tool_name]
    prop_path = details['prop']
    min_val = details.get('min')
    prop_type = details.get('type')

    cameras = _get_active_cameras()
    if not cameras: return

    for cam in cameras:
        cam_data = cam.data
        current_val = _get_nested_attr(cam_data, prop_path)
        if current_val is None: continue

        new_val = current_val + delta
        if prop_type == 'int':
            new_val = int(round(new_val))
        if min_val is not None:
            new_val = max(min_val, new_val)
        
        _set_nested_attr(cam_data, prop_path, new_val)
        _auto_keyframe_if_needed(cam_data, prop_path)
    
    final_value = _get_nested_attr(cameras[0].data, prop_path)
    if final_value is not None:
        osc_feedback.send_active_tool_value_feedback(final_value)

    _force_vse_refresh()

# --- Manejadores para Jog y Plus/Minus ---

def _perform_optics_from_jog(jog_value):
    active_tools = state.control_state.get('active_tools', set())
    if not active_tools: return
    tool_name = next(iter(active_tools))

    if tool_name not in OPTICS_TOOL_PROPERTIES: return
    details = OPTICS_TOOL_PROPERTIES[tool_name]
    
    sensitivity = details['sens_jog']
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_DIVISOR
    
    delta = jog_value * sensitivity
    if details.get('type') == 'rad':
        delta = math.radians(delta)
    
    _apply_property_delta(tool_name, delta)

def _perform_optics_from_plus_minus(direction):
    active_tools = state.control_state.get('active_tools', set())
    if not active_tools: return
    tool_name = next(iter(active_tools))

    if tool_name not in OPTICS_TOOL_PROPERTIES: return
    details = OPTICS_TOOL_PROPERTIES[tool_name]

    sensitivity = details['sens_pm']
    if state.control_state.get('shift_active', False):
        sensitivity /= PRECISION_DIVISOR

    delta = direction * sensitivity
    if details.get('type') == 'rad':
        delta = math.radians(delta)

    _apply_property_delta(tool_name, delta)

# --- Manejadores OSC ---

def handle_optics_tool_activation(address, args):
    """Activa/desactiva una herramienta de óptica y envía feedback."""
    if not args: return
    is_pressed = bool(args[0])
    tool_name = address.strip('/')

    if is_pressed:
        if not _get_active_cameras():
            print(f"OSC Optics: No hay cámara activa para la herramienta '{tool_name}'.")
            return
        bpy.ops.ed.undo_push(message=f"OSC Tool: {tool_name}")
        state.control_state['active_tools'].add(tool_name)
        osc_feedback.send_active_tool_feedback()
        
        # Enviar valor inicial
        if tool_name in OPTICS_TOOL_PROPERTIES:
            prop_path = OPTICS_TOOL_PROPERTIES[tool_name]['prop']
            initial_val = _get_nested_attr(_get_active_cameras()[0].data, prop_path)
            if initial_val is not None:
                osc_feedback.send_active_tool_value_feedback(initial_val)
    else:
        state.control_state['active_tools'].discard(tool_name)
        osc_feedback.send_active_tool_feedback()

def handle_dof_toggle(address, args):
    """Maneja el encendido/apagado del DoF."""
    if not args or not args[0]: return
    
    cameras = _get_active_cameras()
    if not cameras: return

    bpy.ops.ed.undo_push(message="OSC Toggle DOF")
    
    first_cam_new_state = not cameras[0].data.dof.use_dof
    for cam in cameras:
        cam.data.dof.use_dof = first_cam_new_state
        _auto_keyframe_if_needed(cam.data.dof, 'use_dof')
    
    print(f"OSC Optics: DOF {'ACTIVADO' if first_cam_new_state else 'DESACTIVADO'}")
    _force_vse_refresh()

def _handle_optics_keyframe(address, args):
    """Inserta un keyframe en la propiedad de la herramienta óptica activa."""
    if not args or not args[0]: return
    active_tools = state.control_state.get('active_tools', set())
    if not active_tools: return
    tool_name = next(iter(active_tools))

    if tool_name not in OPTICS_TOOL_PROPERTIES: return
    prop_path = OPTICS_TOOL_PROPERTIES[tool_name]['prop']
    
    cameras = _get_active_cameras()
    if not cameras: return
    
    # <-- INICIO: MODIFICACIÓN -->
    # Insertar el keyframe directamente, sin depender de 'auto_record'.
    frame = bpy.context.scene.frame_current
    for cam in cameras:
        try:
            cam.data.keyframe_insert(data_path=prop_path, frame=frame)
        except (TypeError, RuntimeError):
            pass # Falla silenciosamente si la propiedad no es animable
    # <-- FIN: MODIFICACIÓN -->

def _handle_optics_delete_keyframe(address, args):
    """Elimina un keyframe en la propiedad de la herramienta óptica activa."""
    if not args or not args[0]: return
    active_tools = state.control_state.get('active_tools', set())
    if not active_tools: return
    tool_name = next(iter(active_tools))

    if tool_name not in OPTICS_TOOL_PROPERTIES: return
    prop_path = OPTICS_TOOL_PROPERTIES[tool_name]['prop']
    
    cameras = _get_active_cameras()
    if not cameras: return
    
    frame = bpy.context.scene.frame_current
    for cam in cameras:
        try:
            cam.data.keyframe_delete(data_path=prop_path, frame=frame)
        except RuntimeError:
            pass # Falla silenciosamente si no hay keyframe

# --- Registro ---

def register_actions():
    """Registra las acciones de este módulo en el estado global."""
    for tool_name in OPTICS_TOOL_PROPERTIES:
        state.jog_actions[tool_name] = _perform_optics_from_jog
        state.plus_minus_actions[tool_name] = _perform_optics_from_plus_minus
        state.tool_specific_actions[tool_name] = {
            '/key': _handle_optics_keyframe,
            '/del': _handle_optics_delete_keyframe,
        }

def register():
    pass

def unregister():
    pass