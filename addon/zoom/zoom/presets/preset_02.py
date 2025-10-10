# Preset 2 Zoom out entrace

preset_info = {
    "name": "Zoom Out Entrance",
    "author": "Infame",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "zoom": (1, 0, 0),
    "description": "CROSSFADE A>B. CLIP B ENTER WITH A ZOOM OUT."
}

"""

- Requirements:
1. Select exactly two strips.
2. The strips must overlap by at least 2 frames.

- Configuration (Hardcoded):
The 'ZOOM_ANIMATION_PERCENTAGE' variable within this file controls
the duration of the zoom animation as a percentage of the total overlap.
(e.g., 0.66 = the zoom animation lasts 66% of the fade).

- Error Codes:
- E-SEL: Selection Error. Make sure you have two strips selected.
- E-OVRL: Overlap Error. Make sure the strips overlap by at least 2 frames.

"""

import bpy
from .. import osc_feedback

#+++++++++++++++++++++++
# --- CONFIGURATIÓN ---+
#+++++++++++++++++++++++

ZOOM_ANIMATION_PERCENTAGE = 0.66

#+++++++++++++++++++++++


def _create_linear_animation(owner_strip, target_object, data_path, start_frame, end_frame, start_val, end_val):

    try:
        setattr(target_object, data_path, start_val)
        target_object.keyframe_insert(data_path=data_path, frame=start_frame)
        setattr(target_object, data_path, end_val)
        target_object.keyframe_insert(data_path=data_path, frame=end_frame)

        bpy.context.view_layer.update()

        if owner_strip.animation_data and owner_strip.animation_data.action:

            fcurve_path = data_path
            if target_object != owner_strip:
                fcurve_path = f"{target_object.path_from_id()}.{data_path}"

            fcurve = owner_strip.animation_data.action.fcurves.find(fcurve_path)
            if fcurve:
                for kp in fcurve.keyframe_points:
                    if int(kp.co.x) in [start_frame, end_frame]:
                        kp.interpolation = 'LINEAR'
                fcurve.update()
    except Exception as e:
        print(f"Error en _create_linear_animation para '{owner_strip.name}': {e}")

def run(context, *args, **kwargs):
    N = 2
    selected_strips = bpy.context.selected_sequences
    if len(selected_strips) != 2:
        osc_feedback.send("/msg", "E-SEL")
        return
    sorted_strips = sorted(selected_strips, key=lambda s: s.frame_final_start)
    strip_a, strip_b = sorted_strips[0], sorted_strips[1]
    overlap_start, overlap_end = strip_b.frame_final_start, strip_a.frame_final_end
    overlap_duration = overlap_end - overlap_start
    if overlap_duration < 2:
        osc_feedback.send("/msg", "E-OVRL")
        return

    try:
        bpy.ops.ed.undo_push(message=f"Preset {N}: Crossfade Zoom")

        _create_linear_animation(strip_a, strip_a, 'blend_alpha', overlap_start, overlap_end - 1, 1.0, 0.0)
        _create_linear_animation(strip_b, strip_b, 'blend_alpha', overlap_start, overlap_end - 1, 0.0, 1.0)

        if hasattr(strip_b, 'transform'):
            transform = strip_b.transform
            original_scale_x, original_scale_y = transform.scale_x, transform.scale_y
            zoom_end_frame = round(overlap_start + (overlap_duration * ZOOM_ANIMATION_PERCENTAGE))
            start_scale_x, start_scale_y = original_scale_x * 1.5, original_scale_y * 1.5

            _create_linear_animation(strip_b, transform, 'scale_x', overlap_start, zoom_end_frame, start_scale_x, original_scale_x)
            _create_linear_animation(strip_b, transform, 'scale_y', overlap_start, zoom_end_frame, start_scale_y, original_scale_y)

        osc_feedback.send("/msg", f"PRST {N} OK")
    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error en Preset {N}: {e}")