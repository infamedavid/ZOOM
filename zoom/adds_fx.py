# adds_fx.py

import bpy
from . import osc_feedback

# --- ESTRATEGIA DE CONTEXTO (Idéntica a la de adds.py) ---
def get_sequencer_context():
    """
    Busca un área del 'SEQUENCE_EDITOR' y devuelve un contexto
    anulado para que los operadores funcionen correctamente.
    """
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

def _get_contextual_range_and_channel(use_selection):
    """
    Calcula el rango (inicio, fin) y el canal más alto basado en la selección
    o en todos los strips del timeline.
    """
    sequencer = bpy.context.scene.sequence_editor
    if not sequencer:
        return 0, 0, 0

    strips_to_evaluate = []
    if use_selection:
        strips_to_evaluate = bpy.context.selected_sequences
    else:
        strips_to_evaluate = sequencer.sequences_all

    if not strips_to_evaluate:
        return 0, 0, 0

    min_start = min(s.frame_final_start for s in strips_to_evaluate)
    max_end = max(s.frame_final_end for s in strips_to_evaluate)
    highest_channel = max(s.channel for s in strips_to_evaluate)

    return int(min_start), int(max_end), int(highest_channel)


# --- Diccionario Central de Reglas ---
FX_STRIP_RULES = {
    # Efectos de 1 Entrada
    "blur": {"blender_type": "GAUSSIAN_BLUR", "required_selection": 1, "placement_logic": "above_selected"},
    "glow": {"blender_type": "GLOW", "required_selection": 1, "placement_logic": "above_selected"},
    "speed": {"blender_type": "SPEED", "required_selection": 1, "placement_logic": "above_selected_input"},
    "transform": {"blender_type": "TRANSFORM", "required_selection": 1, "placement_logic": "above_selected"},
    "color": {"blender_type": "COLOR", "required_selection": 1, "placement_logic": "above_selected"},
    # Transiciones (2 Entradas)
    "cross": {"blender_type": "CROSS", "required_selection": 2, "placement_logic": "transition"},
    "gamma_cross": {"blender_type": "GAMMA_CROSS", "required_selection": 2, "placement_logic": "transition"},
    "wipe": {"blender_type": "WIPE", "required_selection": 2, "placement_logic": "transition"},
    # Efectos de Capa y Switchers
    "adjustment": {"blender_type": "ADJUSTMENT", "required_selection": ">=0", "placement_logic": "layer_above_context"},
    "multicam": {"blender_type": "MULTICAM", "required_selection": ">=0", "placement_logic": "layer_above_context"},
}


# --- Manejador OSC Principal ---
def handle_add_fx(address, args):
    if not args or not args[0]:
        return

    try:
        effect_name = address.split('/')[-1]
    except IndexError:
        return

    rule = FX_STRIP_RULES.get(effect_name)
    if not rule:
        print(f"OSC Add FX: Efecto desconocido '{effect_name}'")
        return

    sequencer = bpy.context.scene.sequence_editor
    selected_strips = bpy.context.selected_sequences
    
    # --- 1. Validación de Condiciones ---
    req = rule["required_selection"]
    if req == 1 and len(selected_strips) != 1:
        osc_feedback.send_action_feedback("ERROR: NEED 1 STRIP")
        return
    if req == 2 and len(selected_strips) != 2:
        osc_feedback.send_action_feedback("ERROR: NEED 2 STRIPS")
        return
    if req == ">=0" and not sequencer.sequences_all:
        osc_feedback.send_action_feedback("ERROR: NO STRIPS")
        return

    bpy.ops.ed.undo_push(message=f"OSC Add FX: {effect_name.capitalize()}")

    # --- 2. Obtener Contexto Válido ---
    override_context = get_sequencer_context()
    if override_context is None:
        print("OSC Add FX Error: No se encontró un contexto de VSE válido.")
        osc_feedback.send_action_feedback("ERROR: NO VSE")
        bpy.ops.ed.undo()
        return

    # --- 3. Ejecución (dentro del contexto) ---
    try:
        with bpy.context.temp_override(**override_context):
            placement = rule["placement_logic"]

            if placement in ("above_selected", "above_selected_input"):
                source_strip = selected_strips[0]
                bpy.ops.sequencer.effect_strip_add(
                    type=rule["blender_type"],
                    frame_start=source_strip.frame_final_start,
                    frame_end=source_strip.frame_final_end,
                    channel=source_strip.channel + 1
                )
                new_effect = sequencer.active_strip
                new_effect.input_1 = source_strip

            elif placement == "transition":
                strip1, strip2 = sorted(selected_strips, key=lambda s: s.frame_final_start)
                overlap_start = max(strip1.frame_final_start, strip2.frame_final_start)
                overlap_end = min(strip1.frame_final_end, strip2.frame_final_end)

                if overlap_end <= overlap_start:
                    osc_feedback.send_action_feedback("ERROR: NO OVERLAP")
                    bpy.ops.ed.undo()
                    return

                bpy.ops.sequencer.effect_strip_add(
                    type=rule["blender_type"],
                    frame_start=overlap_start,
                    frame_end=overlap_end,
                    channel=max(strip1.channel, strip2.channel) + 1
                )
                new_effect = sequencer.active_strip
                new_effect.input_1 = strip1
                new_effect.input_2 = strip2

            elif placement == "layer_above_context":
                use_selection = bool(selected_strips)
                start, end, channel = _get_contextual_range_and_channel(use_selection)
                bpy.ops.sequencer.effect_strip_add(
                    type=rule["blender_type"],
                    frame_start=start,
                    frame_end=end,
                    channel=channel + 1
                )
        
        osc_feedback.send_action_feedback(f"{effect_name.upper()} ADDED")

    except Exception as e:
        print(f"OSC Add FX: Error al añadir efecto '{effect_name}': {e}")
        osc_feedback.send_action_feedback("ERROR")
        bpy.ops.ed.undo()

def register():
    pass

def unregister():
    pass
