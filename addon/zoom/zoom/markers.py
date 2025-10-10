# markers.py (Con seguimiento de playhead)

import bpy
from . import state
from . import osc_feedback
from . import config

# --- Funciones Auxiliares ---

def _get_marker_at_playhead():
    """
    Busca y devuelve el primer marcador que se encuentre
    exactamente en la posición del cabezal.
    """
    playhead = bpy.context.scene.frame_current
    for marker in bpy.context.scene.timeline_markers:
        if marker.frame == playhead:
            return marker
    return None

def _get_selected_marker():
    """Devuelve el primer marcador seleccionado."""
    for marker in bpy.context.scene.timeline_markers:
        if marker.select:
            return marker
    return None

# --- Manejadores de Lógica Principal ---

def _perform_mark_translate_from_jog(jog_value):
    """Mueve el marcador seleccionado con el jog."""
    marker = _get_selected_marker()
    if not marker: return

    sensitivity = config.MARKER_MOVE_SENSITIVITY_JOG
    if state.control_state.get('shift_active', False):
        sensitivity /= config.PRECISION_DIVISOR

    delta = jog_value * sensitivity

    int_delta = int(round(delta))

    if int_delta != 0:
        marker.frame += int_delta
        # --- INICIO: Lógica de Seguimiento del Cabezal ---
        if state.control_state.get('strip_nav_follow_active', False):
            bpy.context.scene.frame_current = marker.frame
        # --- FIN: Lógica de Seguimiento del Cabezal ---

def _perform_mark_translate_from_plus_minus(direction):
    """Mueve el marcador seleccionado un fotograma a la vez."""
    marker = _get_selected_marker()
    if not marker: return

    marker.frame += direction
    # --- INICIO: Lógica de Seguimiento del Cabezal ---
    if state.control_state.get('strip_nav_follow_active', False):
        bpy.context.scene.frame_current = marker.frame
    # --- FIN: Lógica de Seguimiento del Cabezal ---

# --- Manejadores de Comandos OSC ---

def handle_mark_translate_activation(address, args):
    """Activa la herramienta para mover un marcador."""
    if not args: return
    is_pressed = bool(args[0])
    tool_name = "mark_translate"

    if is_pressed:
        marker = _get_marker_at_playhead()
        if not marker:
            osc_feedback.send_action_feedback("E NO MARK")
            return

        bpy.ops.ed.undo_push(message="OSC Move Marker")

        for m in bpy.context.scene.timeline_markers:
            m.select = False
        marker.select = True

        state.control_state.setdefault('active_tools', set()).add(tool_name)
        osc_feedback.send_active_tool_feedback()
    else:
        state.control_state.setdefault('active_tools', set()).discard(tool_name)
        osc_feedback.send_active_tool_feedback()

def handle_mark_delete(address, args):
    """Elimina el marcador que se encuentra debajo del cabezal."""
    if not args or not args[0]: return

    marker = _get_marker_at_playhead()
    if not marker:
        osc_feedback.send_action_feedback("E NO MARK")
        return

    bpy.ops.ed.undo_push(message="OSC Delete Marker")
    bpy.context.scene.timeline_markers.remove(marker)
    osc_feedback.send_action_feedback("MARK DEL")

# --- Registro ---

def register():
    pass

def unregister():
    pass

def register_actions():
    state.jog_actions['mark_translate'] = _perform_mark_translate_from_jog
    state.plus_minus_actions['mark_translate'] = _perform_mark_translate_from_plus_minus