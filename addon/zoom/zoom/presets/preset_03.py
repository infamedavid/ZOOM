# Preset 3 Zoom in on exit

preset_info = {
    "name": "Zoom In Exit",
    "author": "Infame",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "zoom": (1, 0, 0),
    "description": "CROSSFADE A>B. CLIP A OUT WITH A ZOOM IN."
}

"""
- Requirements:
1. Select exactly two strips.
2. The strips must overlap by at least 2 frames.

- Configuration (Hardcoded):
The variable 'ZOOM_START_PERCENTAGE' controls at what point in the overlap the zoom animation begins.
(e.g., 0.40 = the zoom animation starts 40% of the way through the fade and lasts until the end).

- Error Codes:
- E-SEL: Selection Error.
- E-OVRL: Overlap Error.
"""

import bpy
from .. import osc_feedback

#+++++++++++++++++++++++
# --- CONFIGURATIÓN ---+
#+++++++++++++++++++++++

ZOOM_START_PERCENTAGE = 0.0

#+++++++++++++++++++++++


def _set_linear_interpolation(strip_name, path):
    anim = bpy.context.scene.animation_data
    if anim and anim.action:
        fcurve = anim.action.fcurves.find(
            f'sequence_editor.sequences_all["{strip_name}"].{path}'
        )
        if fcurve:
            for kp in fcurve.keyframe_points:
                kp.interpolation = 'LINEAR'
            fcurve.update()

def run(context, *args, **kwargs):
    N = 3
    selected = bpy.context.selected_sequences
    if len(selected) != 2:
        osc_feedback.send("/msg", "E-SEL"); return
    sorted_strips = sorted(selected, key=lambda s: s.frame_final_start)
    strip_a, strip_b = sorted_strips[0], sorted_strips[1]
    overlap_start, overlap_end = strip_b.frame_final_start, strip_a.frame_final_end
    if (overlap_end - overlap_start) < 2:
        osc_feedback.send("/msg", "E-OVRL"); return

    try:
        bpy.ops.ed.undo_push(message=f"Preset {N}: Zoom In Exit")

        # Crossfade
        strip_a.blend_alpha = 1.0
        strip_a.keyframe_insert(data_path='blend_alpha', frame=overlap_start)
        strip_a.blend_alpha = 0.0
        strip_a.keyframe_insert(data_path='blend_alpha', frame=overlap_end - 1)
        _set_linear_interpolation(strip_a.name, "blend_alpha")

        strip_b.blend_alpha = 0.0
        strip_b.keyframe_insert(data_path='blend_alpha', frame=overlap_start)
        strip_b.blend_alpha = 1.0
        strip_b.keyframe_insert(data_path='blend_alpha', frame=overlap_end - 1)
        _set_linear_interpolation(strip_b.name, "blend_alpha")

        # Zoom In en Clip A
        if hasattr(strip_a, 'transform'):
            transform = strip_a.transform
            original_x, original_y = transform.scale_x, transform.scale_y
            zoom_start = round(overlap_start + ((overlap_end - overlap_start) * ZOOM_START_PERCENTAGE))

            transform.scale_x = original_x
            transform.keyframe_insert(data_path='scale_x', frame=zoom_start)
            transform.scale_x = original_x * 1.5
            transform.keyframe_insert(data_path='scale_x', frame=overlap_end - 1)
            _set_linear_interpolation(strip_a.name, "transform.scale_x")

            transform.scale_y = original_y
            transform.keyframe_insert(data_path='scale_y', frame=zoom_start)
            transform.scale_y = original_y * 1.5
            transform.keyframe_insert(data_path='scale_y', frame=overlap_end - 1)
            _set_linear_interpolation(strip_a.name, "transform.scale_y")

        osc_feedback.send("/msg", f"PRST {N} OK")
    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error en Preset {N}: {e}")
