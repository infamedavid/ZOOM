# fades.py

import bpy
import math
from . import state
from . import config

# --- Funciones Auxiliares ---

def _get_visible_range(strip):
    """
    Devuelve el rango visible (start, end) de un strip.
    """
    if hasattr(strip, "frame_final_start") and hasattr(strip, "frame_final_end"):
        return int(strip.frame_final_start), int(strip.frame_final_end)
    else:
        start = int(strip.frame_start + getattr(strip, "frame_offset_start", 0))
        end = int(start + strip.frame_final_duration)
        return start, end

def _create_fade(strip, property_name, start_frame, end_frame, start_val, end_val):
    """
    Inserta keyframes en la propiedad de un strip y ajusta interpolación.
    """
    if not strip or not hasattr(strip, property_name) or start_frame >= end_frame:
        return

    try:
        curve_type = state.control_state.get("fade_curve_type", "LINEAR")

        # Insertar keyframes
        setattr(strip, property_name, start_val)
        strip.keyframe_insert(data_path=property_name, frame=start_frame)

        setattr(strip, property_name, end_val)
        strip.keyframe_insert(data_path=property_name, frame=end_frame)

        # Ajustar interpolación en los keyframes recién creados
        ad = bpy.context.scene.sequence_editor.animation_data
        if ad and ad.action:
            fcurve = ad.action.fcurves.find(
                data_path=f'sequence_editor.sequences_all["{strip.name}"].{property_name}'
            )
            if fcurve:
                for kp in fcurve.keyframe_points:
                    if math.isclose(kp.co.x, start_frame) or math.isclose(kp.co.x, end_frame):
                        kp.interpolation = curve_type
                        if curve_type == "BEZIER":
                            kp.handle_left_type = "AUTO"
                            kp.handle_right_type = "AUTO"
                fcurve.update()

    except Exception as e:
        print(f"OSC Fades: Error al crear fundido en '{strip.name}': {e}")

def _are_strips_compatible(strip_a, strip_b):
    """
    Comprueba si dos strips son compatibles para un crossfade (ambos visuales o ambos de audio).
    Devuelve "VISUAL", "AUDIO" o None.
    """
    VISUAL_TYPES = {'MOVIE', 'IMAGE', 'COLOR', 'SCENE', 'META'}
    AUDIO_TYPES = {'SOUND', 'META', 'SCENE'}

    a_is_visual = strip_a.type in VISUAL_TYPES
    b_is_visual = strip_b.type in VISUAL_TYPES
    a_is_audio = strip_a.type in AUDIO_TYPES
    b_is_audio = strip_b.type in AUDIO_TYPES

    if a_is_visual and b_is_visual:
        return "VISUAL"
    if a_is_audio and b_is_audio:
        return "AUDIO"

    return None

# --- Manejadores OSC ---

def handle_fade_in_to_cursor(address, args):
    if not args or not args[0]:
        return

    selected_strips = bpy.context.selected_sequences
    cursor_frame = bpy.context.scene.frame_current

    if not selected_strips:
        return
    bpy.ops.ed.undo_push(message="OSC Fade In to Cursor")

    for strip in selected_strips:
        start_frame, _ = _get_visible_range(strip)
        end_fade_frame = cursor_frame

        if end_fade_frame <= start_frame:
            continue

        if hasattr(strip, "blend_alpha"):
            _create_fade(strip, "blend_alpha", start_frame, end_fade_frame, 0.0, 1.0)
        if hasattr(strip, "volume"):
            _create_fade(strip, "volume", start_frame, end_fade_frame, 0.0, 1.0)

def handle_fade_out_from_cursor(address, args):
    if not args or not args[0]:
        return

    selected_strips = bpy.context.selected_sequences
    cursor_frame = bpy.context.scene.frame_current

    if not selected_strips:
        return
    bpy.ops.ed.undo_push(message="OSC Fade Out from Cursor")

    for strip in selected_strips:
        _, end_frame = _get_visible_range(strip)
        start_fade_frame = cursor_frame

        if start_fade_frame >= end_frame - 1:
            continue

        if hasattr(strip, "blend_alpha"):
            _create_fade(strip, "blend_alpha", start_fade_frame, end_frame - 1, 1.0, 0.0)
        if hasattr(strip, "volume"):
            _create_fade(strip, "volume", start_fade_frame, end_frame - 1, 1.0, 0.0)

def handle_crossfade_from_overlap(address, args):
    if not args or not args[0]:
        return

    selected_strips = list(bpy.context.selected_sequences)
    if len(selected_strips) < 2:
        return

    bpy.ops.ed.undo_push(message="OSC Crossfade Overlaps")

    visual_strips = sorted(
        [s for s in selected_strips if s.type in {'MOVIE', 'IMAGE', 'COLOR', 'SCENE', 'META'}],
        key=lambda s: (_get_visible_range(s)[0], _get_visible_range(s)[1])
    )
    audio_strips = sorted(
        [s for s in selected_strips if s.type in {'SOUND', 'META', 'SCENE'}],
        key=lambda s: (_get_visible_range(s)[0], _get_visible_range(s)[1])
    )

    groups_to_process = [
        ("VISUAL", visual_strips),
        ("AUDIO", audio_strips)
    ]

    for group_type, group_strips in groups_to_process:
        for i in range(len(group_strips) - 1):
            strip_a = group_strips[i]
            strip_b = group_strips[i+1]

            # Regla de exclusión: Strips bloqueados o muteados
            if strip_a.lock or strip_b.lock or strip_a.mute or strip_b.mute:
                continue

            start_a, end_a = _get_visible_range(strip_a)
            start_b, end_b = _get_visible_range(strip_b)

            overlap_start = max(start_a, start_b)
            overlap_end = min(end_a, end_b)
            overlap_duration = overlap_end - overlap_start

            # Solapamiento mínimo
            if overlap_duration < config.MIN_FADE_DURATION:
                continue

            # Strips contenidos
            a_contains_b = start_a <= start_b and end_a >= end_b
            b_contains_a = start_b <= start_a and end_b >= end_a
            if a_contains_b or b_contains_a:
                continue

            # Definir salida/entrada
            out_strip, in_strip = strip_a, strip_b
            property_name = "blend_alpha" if group_type == "VISUAL" else "volume"

            if hasattr(out_strip, property_name) and hasattr(in_strip, property_name):
                _create_fade(out_strip, property_name, overlap_start, overlap_end - 1, 1.0, 0.0)
                _create_fade(in_strip, property_name, overlap_start, overlap_end - 1, 0.0, 1.0)

def handle_fade_curve_toggle(address, args):
    if not args or not isinstance(args[0], bool):
        return

    use_bezier = args[0]
    new_type = "BEZIER" if use_bezier else "LINEAR"

    state.control_state["fade_curve_type"] = new_type
    print(f"OSC Fades: Tipo de curva establecido a '{new_type}'")

def register():
    pass

def unregister():
    pass

def register_actions():
    pass