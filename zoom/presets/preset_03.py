# Preset 3 Zoom in on exit

"""
PRESET 03: TRANSICIÓN CON ZOOM IN ("Zoom In Exit")

- Descripción:
  Aplica un efecto de salida al primer clip (Clip A) basado en el
  solapamiento (overlap) con el segundo clip (Clip B).
  Se crea un crossfade estándar (A se desvanece, B aparece) y,
  simultáneamente, el Clip A hace una animación de Zoom In.

- Requisitos:
  1. Seleccionar exactamente dos strips.
  2. Los strips deben tener un solapamiento de al menos 2 frames.

- Configuración (Hardcoded):
  La variable 'ZOOM_START_PERCENTAGE' controla en qué punto del
  overlap comienza la animación de zoom.
  (ej. 0.40 = la animación de zoom empieza cuando ha transcurrido
   el 40% del fundido y dura hasta el final).

- Códigos de Error:
  - E-SEL: Error de Selección.
  - E-OVRL: Error de Overlap.
"""

import bpy
from .. import osc_feedback

ZOOM_START_PERCENTAGE = 0.0

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
