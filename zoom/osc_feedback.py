# osc_feedback.py (Actualizado)

import bpy
import math
import time
from pythonosc import udp_client
from . import state
from bpy.app.handlers import persistent

# <-- INICIO: MAPA DE NOMBRES Y LÓGICA DE FEEDBACK -->

# Diccionario para traducir nombres internos a etiquetas de la superficie.
TOOL_NAME_MAP = {
    # tools_extra
    "zoom": "ZOOM", "posx": "POS X", "posy": "POS Y", "rot": "ROT",
    "origx": "ORGN X", "origy": "ORGN Y", "alpha": "OPCT", "blend": "BL TYPE",
    "crop_l": "CROP L", "crop_r": "CROP R", "crop_t": "CROP TP", "crop_b": "CROP BT",
    "mirror_x": "MIR X", "mirror_y": "MIR Y", "reverse": "REV", "saturation": "SAT",
    "multiply": "GAIN", "off_start": "OFST ST", "off_end": "OFST END",
    # Herramientas de Audio
    "volume": "VOLUME","pan": "PAN",
    # strips_tools
    "translate": "GRAB", "ripple_move": "KNIFE SFT", # Default para ripple_move
    # strips_advance
    "ripple": "HEAP", "splice_trim": "SPLICE", "insert": "INSERT",
    # offsets_tools
    "slip": "SLIP", "push": "TAIL DRIF", "pull": "HEAD DRIF",
    "sleat": "SLEAT", "slide": "SLIDE",
    # bl_cam & bl_cam_prop
    "dolly": "DOLLY", "truck": "TRUCK", "pedestal": "PDSTL", "pan": "PAN",
    "tilt": "TILT", "roll": "ROLL", "camera": "CAME CUT",
    # Modo especial
    "navigate": "STRIP SEL"
}

def send(address, value):
    """
    Envía un mensaje OSC desde Blender a la superficie de control.
    """
    if not hasattr(bpy.context.scene, "osc_vse_properties"): return
    props = bpy.context.scene.osc_vse_properties
    client_ip, client_port = props.client_ip, props.client_port
    if not client_ip or client_port <= 0: return
    try:
        client = udp_client.SimpleUDPClient(client_ip, client_port)
        client.send_message(address, value)
    except Exception as e:
        print(f"OSC Feedback Error: No se pudo enviar mensaje a {client_ip}:{client_port} - {e}")

def send_active_tool_feedback():
    """
    Consulta el estado, traduce el nombre de la herramienta activa y lo envía.
    Maneja los casos especiales como KNIFE y el estado "ninguno".
    """
    tool_name_internal = "none"
    display_name = "        "

    # Prioridad 1: Nombre personalizado (para casos como KNIFE SFT/HRD)
    custom_name = state.control_state.get('active_tool_custom_name')
    if custom_name:
        display_name = custom_name
    else:
        # Prioridad 2: Modo de navegación
        if state.control_state.get('strip_nav_active', False):
            tool_name_internal = "navigate"
        # Prioridad 3: Herramientas del set 'active_tools'
        else:
            active_tools = state.control_state.get('active_tools', set())
            if active_tools:
                tool_name_internal = next(iter(active_tools))
        
        if tool_name_internal != "none":
            display_name = TOOL_NAME_MAP.get(tool_name_internal, tool_name_internal.upper())

    send("/active_tool", display_name)
    state.control_state['last_sent_tool'] = display_name # Guardar para el monitor de estado

def send_active_tool_value_feedback(value):
    """
    Envía el valor numérico de la herramienta activa (usado por ahora solo para óptica).
    """
    try:
        formatted_value = f"{float(value):.3f}"
        send("/active_tool/value", formatted_value)
    except (ValueError, TypeError):
        send("/active_tool/value", str(value))

def send_action_feedback(message):
    """
    Envía un feedback de evento momentáneo (flash) a la superficie.
    """
    def clear_feedback():
        send("/action_feedback", " ")
        return None # El timer se ejecuta solo una vez

    send("/action_feedback", message.upper())
    bpy.app.timers.register(clear_feedback, first_interval=1.0)

# <-- FIN: MAPA DE NOMBRES Y LÓGICA DE FEEDBACK -->

@persistent
def timecode_frame_change_handler(scene):
    # ... (El resto de esta función no cambia)
    if not state.control_state.get("timecode_feedback_active"): return
    now = time.time()
    if now - state.control_state.get("timecode_last_send_time", 0.0) < 0.1: return
    state.control_state["timecode_last_send_time"] = now
    render = scene.render
    frame_current, fps, fps_base = scene.frame_current, render.fps, render.fps_base
    if fps == 0 or fps_base == 0: return
    effective_fps = fps / fps_base
    if effective_fps == 0: return
    total_seconds = (frame_current - 1) / effective_fps
    m, s = divmod(total_seconds, 60)
    h, m = divmod(m, 60)
    frame = (frame_current - 1) % round(effective_fps) if effective_fps > 0 else 0
    timecode_str = f"{int(h):02d}:{int(m):02d}:{int(s):02d}:{int(frame):02d}"
    send("/timecode_display", timecode_str)