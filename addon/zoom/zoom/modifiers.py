# modifiers.py

"""
Módulo para la gestión avanzada de modificadores de strip en el VSE.
Implementa un sistema de inspección, adición y edición remota vía OSC
basado en el strip activo.
"""

import bpy
import math
import colorsys
from . import state
from . import osc_feedback



# Mapea el .type de Blender al sufijo del mensaje OSC de feedback
MODIFIER_TYPE_MAP = {
    'BRIGHT_CONTRAST': 'brightcontrast',
    'COLOR_BALANCE': 'color_balance',
    'WHITE_BALANCE': 'white_balance',
    'CURVES': 'curves',
    'HUE_CORRECT': 'hue_correct',
    'SOUND_EQUALIZER': 'equalizer',
}

# Mapea el sufijo del mensaje OSC /add_ al .type de Blender
ADD_MODIFIER_MAP = {
    'brightcontrast': ('Bright/Contrast', 'BRIGHT_CONTRAST'),
    'color_balance': ('Color Balance', 'COLOR_BALANCE'),
    'white_balance': ('White Balance', 'WHITE_BALANCE'),
    'curves': ('Curves', 'CURVES'),
    'hue_correct': ('Hue Correct', 'HUE_CORRECT'),
    'equalizer': ('Equalizer', 'SOUND_EQUALIZER'),
}

# --- FUNCIONES AUXILIARES ---

def _get_vse_context():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override_context = {
                            'window': window,
                            'screen': window.screen,
                            'area': area,
                            'region': region,
                            'space_data': area.spaces.active,
                        }
                        return override_context
    return None

def _get_active_strip_and_modifier():
    strip_name = state.control_state.get('active_modifier_strip_name')
    modifier_idx = state.control_state.get('active_modifier_stack_index')

    if strip_name is None or modifier_idx is None:
        return None, None

    try:
        sequencer = bpy.context.scene.sequence_editor
        strip = sequencer.sequences_all.get(strip_name)
        if not strip:
            return None, None
        modifier = strip.modifiers[modifier_idx]
        return strip, modifier
    except (AttributeError, IndexError):
        return None, None

def xy_to_rgb(x, y):
    r = math.sqrt(x*x + y*y)
    if r > 1:
        x /= r; y /= r; r = 1

    angle = -math.atan2(y, x) + math.pi / 2
    hue = (angle / (2 * math.pi)) % 1.0
    sat = r
    val = 1.0
    return colorsys.hsv_to_rgb(hue, sat, val)

# --- MANEJADORES OSC PRINCIPALES ---

def handle_modifier_inspect(address, args):
    """Manejador para la "Pregunta": /strip/modifier/inspect/I"""
    if not args or not args[0]:
        return

    try:
        parts = address.strip('/').split('/')
        modifier_idx = int(parts[3])
    except (ValueError, IndexError):
        print(f"OSC Modifiers: Dirección de inspección inválida: {address}")
        return

    active_strip = bpy.context.scene.sequence_editor.active_strip
    if not active_strip:
        print("OSC Modifiers: No hay strip activo para inspeccionar.")
        return

    # Limpiar estados de herramientas de modificador anteriores
    _clear_curve_state()
    state.control_state['active_modifier_strip_name'] = active_strip.name
    state.control_state['active_modifier_stack_index'] = modifier_idx

    try:
        modifier = active_strip.modifiers[modifier_idx]
        mod_type_str = MODIFIER_TYPE_MAP.get(modifier.type, "unknown")

        osc_feedback.send(f"/modifier_{mod_type_str}", 1)
        print(f"OSC Inspect: Encontrado '{modifier.name}' ({modifier.type}) en strip '{active_strip.name}' en el índice {modifier_idx}.")

        # --- LÓGICA DE SINCRONIZACIÓN ESPECÍFICA ---
        if modifier.type == 'COLOR_BALANCE':
            # ... (esta parte no cambia)
            mode = modifier.color_balance.correction_method
            lift = modifier.color_balance.lift if mode == 'LIFT_GAMMA_GAIN' else modifier.color_balance.offset
            gamma = modifier.color_balance.gamma if mode == 'LIFT_GAMMA_GAIN' else modifier.color_balance.power
            gain = modifier.color_balance.gain if mode == 'LIFT_GAMMA_GAIN' else modifier.color_balance.slope
            osc_feedback.send("/fb_lift", list(lift))
            osc_feedback.send("/fb_gamma", list(gamma))
            osc_feedback.send("/fb_gain", list(gain))

        elif modifier.type == 'CURVES':
            _sync_curve_state_from_modifier(modifier)

        elif modifier.type == 'EQUALIZER':
            _sync_eq_state_from_modifier(modifier)

    except (AttributeError, IndexError):
        osc_feedback.send("/modifier_none", 1)
        print(f"OSC Inspect: Strip '{active_strip.name}' no tiene modificador en el índice {modifier_idx}.")


def handle_modifier_add(address, args):
    if not args or not args[0]:
        return

    type_suffix = address.split('/')[-1].replace('add_', '')
    mod_info = ADD_MODIFIER_MAP.get(type_suffix)
    if not mod_info:
        print(f"OSC Modifiers: Tipo de modificador para añadir desconocido: {type_suffix}")
        return

    mod_name, mod_type = mod_info
    strip_name = state.control_state.get('active_modifier_strip_name')
    if not strip_name:
        print("OSC Modifiers: No se puede añadir, no hay strip activo en el contexto.")
        return

    strip = bpy.context.scene.sequence_editor.sequences_all.get(strip_name)
    if not strip:
        print(f"OSC Modifiers: El strip '{strip_name}' del contexto ya no existe.")
        return

    try:
        bpy.ops.ed.undo_push(message=f"OSC Add Modifier {mod_name}")
        new_modifier = strip.modifiers.new(name=mod_name, type=mod_type)
        new_modifier_index = len(strip.modifiers) - 1
        state.control_state['active_modifier_stack_index'] = new_modifier_index
        print(f"OSC Add: Añadido '{new_modifier.name}' a '{strip.name}'. Índice {new_modifier_index}.")
        osc_feedback.send(f"/modifier_{type_suffix}", new_modifier.name)
    except Exception as e:
        print(f"OSC Add: Error al añadir modificador: {e}")


def handle_modifier_global_op(address, args):
    if not args or not args[0]:
        return

    strip, modifier = _get_active_strip_and_modifier()
    if not strip or not modifier:
        print("OSC Global Op: No hay modificador activo para operar.")
        return

    op_type = address.split('/')[-1]

    bpy.ops.ed.undo_push(message=f"OSC Modifier Op: {op_type}")

    if op_type == "modifier_toggle_mute":
        modifier.mute = not modifier.mute

    elif op_type == "modifier_delete":
        strip.modifiers.remove(modifier)
        state.control_state['active_modifier_strip_name'] = None
        state.control_state['active_modifier_stack_index'] = None
        print("OSC Global Op: Modificador borrado. Contexto limpiado.")

    elif op_type in ["modifier_move_up", "modifier_move_down"]:
        direction = 'UP' if op_type == "modifier_move_up" else 'DOWN'

        context_override = _get_vse_context()
        if context_override:
            try:
                with bpy.context.temp_override(**context_override):
                    bpy.ops.sequencer.strip_modifier_move(name=modifier.name, direction=direction)

                for i, mod in enumerate(strip.modifiers):
                    if mod == modifier:
                        state.control_state['active_modifier_stack_index'] = i
                        print(f"OSC Global Op: Modificador movido a índice {i}. State actualizado.")
                        break
            except Exception as e:
                print(f"OSC Error al mover modificador: {e}")
        else:
            print("OSC Error: No se pudo encontrar el contexto del Sequencer para mover el modificador.")

def handle_modifier_edit(address, args):
    strip, modifier = _get_active_strip_and_modifier()
    if not strip or not modifier:
        return
    if not args:
        return

    if modifier.type == 'COLOR_BALANCE':
        mode = modifier.color_balance.correction_method

        if address == "/modifier_toggle_correction_method" and args[0]:
            modifier.color_balance.correction_method = 'OFFSET_POWER_SLOPE' if mode == 'LIFT_GAMMA_GAIN' else 'LIFT_GAMMA_GAIN'
            return
        if address == "/modifier_invert_lift" and args[0]:
            modifier.color_balance.invert_lift = not modifier.color_balance.invert_lift
            return
        if address == "/modifier_invert_gamma" and args[0]:
            modifier.color_balance.invert_gamma = not modifier.color_balance.invert_gamma
            return
        if address == "/modifier_invert_gain" and args[0]:
            modifier.color_balance.invert_gain = not modifier.color_balance.invert_gain
            return

        master_prop = None
        if address == '/modifier_lift_master':
            master_prop = 'lift' if mode == 'LIFT_GAMMA_GAIN' else 'offset'
        elif address == '/modifier_gamma_master':
            master_prop = 'gamma' if mode == 'LIFT_GAMMA_GAIN' else 'power'
        elif address == '/modifier_gain_master':
            master_prop = 'gain' if mode == 'LIFT_GAMMA_GAIN' else 'slope'

        if master_prop:
            current_rgb = getattr(modifier.color_balance, master_prop)
            current_hsv = list(colorsys.rgb_to_hsv(*current_rgb))
            new_value = float(args[0])
            current_hsv[2] = new_value
            new_rgb = colorsys.hsv_to_rgb(*current_hsv)
            setattr(modifier.color_balance, master_prop, new_rgb)
            return

        if len(args) >= 2:
            rgb = xy_to_rgb(float(args[0]), float(args[1]))
            color_prop = None
            if address == "/modifier_lift":
                color_prop = 'lift' if mode == 'LIFT_GAMMA_GAIN' else 'offset'
                feedback = "/fb_lift"
            elif address == "/modifier_gamma":
                color_prop = 'gamma' if mode == 'LIFT_GAMMA_GAIN' else 'power'
                feedback = "/fb_gamma"
            elif address == "/modifier_gain":
                color_prop = 'gain' if mode == 'LIFT_GAMMA_GAIN' else 'slope'
                feedback = "/fb_gain"
            else:
                feedback = None

            if color_prop:
                current_color = getattr(modifier.color_balance, color_prop)
                current_hsv = colorsys.rgb_to_hsv(*current_color)
                new_hsv = colorsys.rgb_to_hsv(*rgb)
                final_rgb = colorsys.hsv_to_rgb(new_hsv[0], new_hsv[1], current_hsv[2])
                setattr(modifier.color_balance, color_prop, final_rgb)

                if feedback:
                    osc_feedback.send(feedback, list(final_rgb))
            return

    elif modifier.type == 'BRIGHT_CONTRAST':
        if address == '/modifier_bright':
            modifier.bright = float(args[0]); return
        if address == '/modifier_contrast':
            modifier.contrast = float(args[0]); return

    elif modifier.type == 'WHITE_BALANCE':
        if address == '/modifier_white_r':
            modifier.white_balance.color_value[0] = float(args[0]); return
        if address == '/modifier_white_g':
            modifier.white_balance.color_value[1] = float(args[0]); return
        if address == '/modifier_white_b':
            modifier.white_balance.color_value[2] = float(args[0]); return


# ---Curvas de color ----

def _clear_curve_state():
    state.control_state['active_curve_channel'] = None
    state.control_state['active_curve_node_index'] = None
    state.control_state['active_curve_node_slot'] = None

def _send_curve_feedback(channel_char, curve):
    if not curve or not hasattr(curve, 'points'):
        return

    points_coords = [[p.location.x, p.location.y] for p in curve.points]
    osc_feedback.send(f"/fb_curve{channel_char}_nodes", points_coords)

def _sync_curve_state_from_modifier(modifier):
    if not modifier or modifier.type != 'CURVES':
        return

    curves_map = {
        'R': modifier.curve_mapping.curves[0],
        'G': modifier.curve_mapping.curves[1],
        'B': modifier.curve_mapping.curves[2],
        'C': modifier.curve_mapping.curves[3],
    }

    for channel, curve_obj in curves_map.items():
        _send_curve_feedback(channel, curve_obj)

    print("OSC Curves: Estado de curvas sincronizado y feedback enviado.")

def _get_active_curve():
    strip, modifier = _get_active_strip_and_modifier()
    channel = state.control_state.get('active_curve_channel')
    node_idx = state.control_state.get('active_curve_node_index')

    if not all([strip, modifier, channel]) or node_idx is None:
        return None, None

    if modifier.type != 'CURVES':
        return None, None

    try:
        curves_map = {'R': 0, 'G': 1, 'B': 2, 'C': 3}
        curve_index = curves_map.get(channel)
        if curve_index is None: return None, None

        curve = modifier.curve_mapping.curves[curve_index]
        node = curve.points[node_idx]
        return curve, node
    except (IndexError, KeyError):
        return None, None

def _handle_curve_node_selection(channel, slot, is_pressed):
    if not is_pressed:
        _clear_curve_state()
        return

    strip, modifier = _get_active_strip_and_modifier()
    if not strip or not modifier or modifier.type != 'CURVES':
        print("OSC Curves: No hay un modificador de curvas activo.")
        return

    bpy.ops.ed.undo_push(message=f"OSC Select Curve Node {channel}{slot}")

    curves_map = {'R': 0, 'G': 1, 'B': 2, 'C': 3}
    curve_index = curves_map.get(channel)
    if curve_index is None: return

    curve = modifier.curve_mapping.curves[curve_index]

    state.control_state['active_curve_channel'] = channel
    state.control_state['active_curve_node_slot'] = slot

    node_positions = {
        1: 0,
        5: -1
    }

    if slot in node_positions:
        node_idx = node_positions[slot]
        if node_idx == -1:
            node_idx = len(curve.points) - 1
        state.control_state['active_curve_node_index'] = node_idx

    elif 2 <= slot <= 4:
        slot_x_defaults = {2: 0.25, 3: 0.5, 4: 0.75}
        target_x = slot_x_defaults[slot]

        existing_node_idx = None
        for i, point in enumerate(curve.points[1:-1]):
            if math.isclose(point.location.x, target_x, abs_tol=0.01):
                existing_node_idx = i + 1
                break

        if existing_node_idx is not None:
            state.control_state['active_curve_node_index'] = existing_node_idx
        else:
            if len(curve.points) < 5:
                new_point = curve.points.new(target_x, target_x)
                # Ordenar puntos manualmente (ya no existe curve.update())
                sorted_points = sorted(curve.points, key=lambda p: p.location.x)
                new_node_idx = sorted_points.index(new_point)
                state.control_state['active_curve_node_index'] = new_node_idx
            else:
                print("OSC Curves: Límite de 3 nodos intermedios alcanzado.")
                _clear_curve_state()
                return

    _send_curve_feedback(channel, curve)

def _handle_curve_xy_edit(channel, x, y):
    if state.control_state.get('active_curve_channel') != channel:
        return

    curve, node = _get_active_curve()
    if not curve or not node:
        return

    node.location.x = max(0.0, min(1.0, float(x)))
    node.location.y = max(0.0, min(1.0, float(y)))

    _send_curve_feedback(channel, curve)

def _handle_curve_node_reset():
    curve, node = _get_active_curve()
    slot = state.control_state.get('active_curve_node_slot')
    if not curve or not node or not slot:
        return

    bpy.ops.ed.undo_push(message="OSC Reset Curve Node")

    default_positions = {
        1: (0.0, 0.0), 2: (0.25, 0.25), 3: (0.5, 0.5),
        4: (0.75, 0.75), 5: (1.0, 1.0)
    }

    if slot in default_positions:
        node.location.x, node.location.y = default_positions[slot]

        _send_curve_feedback(state.control_state['active_curve_channel'], curve)

def _handle_curve_node_delete():
    curve, node = _get_active_curve()
    slot = state.control_state.get('active_curve_node_slot')

    if not curve or not node or not slot or slot in [1, 5]:
        print("OSC Curves: No se puede borrar. Solo nodos intermedios (2, 3, 4) son borrables.")
        return

    bpy.ops.ed.undo_push(message="OSC Delete Curve Node")

    curve.points.remove(node)


    channel = state.control_state.get('active_curve_channel')
    _clear_curve_state()
    _send_curve_feedback(channel, curve)

def handle_curve_command(address, args):
    try:
        parts = address.strip('/').split('_')

        # Canal detectado en la dirección OSC
        channel_char = parts[0][-1].upper()
        if channel_char not in ['C', 'R', 'G', 'B']:
            channel_char = 'C'

        # Mapeo correcto al índice interno de Blender
        curves_map = {
            'R': 0,
            'G': 1,
            'B': 2,
            'C': 3,
        }

        op = parts[1]

        if op.startswith('node'):
            slot = int(op.replace('node', ''))
            is_pressed = bool(args[0]) if args else False
            _handle_curve_node_selection(channel_char, slot, is_pressed)

        elif op == 'xy':
            if not args or len(args) < 2:
                return
            _handle_curve_xy_edit(channel_char, args[0], args[1])

        elif op == 'reset':
            if not args or not args[0]:
                return
            _handle_curve_node_reset()

        elif op == 'delete':
            if not args or not args[0]:
                return
            _handle_curve_node_delete()

        # Refresco
        strip, modifier = _get_active_strip_and_modifier()
        if modifier and modifier.type == 'CURVES':
            modifier.curve_mapping.update()
            for area in bpy.context.screen.areas:
                if area.type == 'SEQUENCE_EDITOR':
                    area.tag_redraw()

        if strip and hasattr(strip, 'mute'):
            original_mute = strip.mute
            strip.mute = not original_mute
            strip.mute = original_mute


    except (IndexError, ValueError) as e:
        print(f"OSC Curves: Comando inválido '{address}': {e}")

# =====================================================================
# == BANDAS  ECUALIZADOR (EQUALIZER)
# =====================================================================

def _sync_eq_state_from_modifier(modifier):
    """Inicializa siempre 3 bandas fijas en el ecualizador (Low, Mid, High)."""
    if not modifier or modifier.type != 'SOUND_EQUALIZER':
        return

    # Limpia todas las bandas actuales
    modifier.clear_soundeqs()

    # Definimos tres rangos clásicos
    bands = [
        (20.0, 300.0),       # Low
        (300.0, 3000.0),     # Mid
        (3000.0, 20000.0)    # High
    ]

    for lo, hi in bands:
        modifier.new_graphic(lo, hi)

    # Feedback inicial: solo devolvemos los rangos
    osc_feedback.send("/fb/eq/bands", bands)
    print("OSC EQ: 3 bandas inicializadas y sincronizadas.")


def _handle_eq_band_edit(band_index, slider_value):
    """
    Ajusta dinámicamente el rango de la banda.
    El slider_value (0.0–1.0) define un factor de escala sobre la banda base.
    """
    strip, modifier = _get_active_strip_and_modifier()
    if not modifier or modifier.type != 'SOUND_EQUALIZER':
        return

    if band_index < 0 or band_index >= 3:
        return

    # Rangos base
    base_bands = [
        (20.0, 300.0),       # Low
        (300.0, 3000.0),     # Mid
        (3000.0, 20000.0)    # High
    ]

    # Escalamos el rango según el slider
    lo, hi = base_bands[band_index]
    width = hi - lo
    scale = 0.5 + slider_value  # entre 0.5x y 1.5x
    center = (lo + hi) / 2.0
    new_lo = max(20.0, center - (width * scale / 2))
    new_hi = min(20000.0, center + (width * scale / 2))

    # Volvemos a crear todas las bandas, modificando solo la indicada
    modifier.clear_soundeqs()
    new_bands = list(base_bands)
    new_bands[band_index] = (new_lo, new_hi)
    for lo, hi in new_bands:
        modifier.new_graphic(lo, hi)

    lo, hi = new_bands[band_index]
    osc_feedback.send(f"/fb/eq/band{band_index+1}/lo", lo)
    osc_feedback.send(f"/fb/eq/band{band_index+1}/hi", hi)

    print(f"OSC EQ: Banda {band_index+1} reconfigurada → {new_lo:.1f}–{new_hi:.1f} Hz")



def _handle_eq_reset_all():
    """Resetea las tres bandas a sus rangos base."""
    strip, modifier = _get_active_strip_and_modifier()
    if not modifier or modifier.type != 'SOUND_EQUALIZER':
        return

    modifier.clear_soundeqs()
    base_bands = [
        (20.0, 300.0),
        (300.0, 3000.0),
        (3000.0, 20000.0)
    ]
    for idx, (lo, hi) in enumerate(base_bands):
        modifier.new_graphic(lo, hi)
        osc_feedback.send(f"/fb/eq/band{idx+1}/lo", lo)
        osc_feedback.send(f"/fb/eq/band{idx+1}/hi", hi)

    print("OSC EQ: Todas las bandas reseteadas a valores base.")



def handle_eq_command(address, args):
    """Super-manejador que enruta todos los comandos /eq/*."""
    try:
        parts = address.strip('/').split('/')
        op = parts[1]

        if op == 'band':
            band_index = int(parts[2]) - 1  # 1→0, 2→1, 3→2
            value = float(args[0]) if args else 0.0
            _handle_eq_band_edit(band_index, value)

        elif op == 'reset_all':
            if not args or not args[0]:
                return
            _handle_eq_reset_all()

    except (IndexError, ValueError) as e:
        print(f"OSC EQ: Comando inválido '{address}': {e}")



def register():
    pass

def unregister():
    pass