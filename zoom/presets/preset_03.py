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

# --- CONFIGURACIÓN ---
# Define en qué punto del overlap (0.0 a 1.0) comienza el zoom in.
ZOOM_START_PERCENTAGE = 0.40

def run(context, *args, **kwargs):
    N = 3

    selected_strips = bpy.context.selected_sequences
    if len(selected_strips) != 2:
        osc_feedback.send("/msg", "E-SEL")
        return

    sorted_strips = sorted(selected_strips, key=lambda s: s.frame_final_start)
    strip_a = sorted_strips[0] # Outgoing
    strip_b = sorted_strips[1] # Incoming

    overlap_start = strip_b.frame_final_start
    overlap_end = strip_a.frame_final_end
    overlap_duration = overlap_end - overlap_start

    if overlap_duration < 2:
        osc_feedback.send("/msg", "E-OVRL")
        return

    try:
        bpy.ops.ed.undo_push(message=f"Preset {N}: Zoom In Exit")

        # --- Animación de Crossfade (Alpha) ---
        # Fade Out en Clip A
        if hasattr(strip_a, 'blend_alpha'):
            strip_a.blend_alpha = 1.0
            strip_a.keyframe_insert(data_path='blend_alpha', frame=overlap_start)
            strip_a.blend_alpha = 0.0
            strip_a.keyframe_insert(data_path='blend_alpha', frame=overlap_end - 1)
            if strip_a.animation_data and strip_a.animation_data.action:
                fcurve = strip_a.animation_data.action.fcurves.find('blend_alpha')
                if fcurve:
                    for kp in fcurve.keyframe_points: kp.interpolation = 'LINEAR'
                    fcurve.update()

        # Fade In en Clip B
        if hasattr(strip_b, 'blend_alpha'):
            strip_b.blend_alpha = 0.0
            strip_b.keyframe_insert(data_path='blend_alpha', frame=overlap_start)
            strip_b.blend_alpha = 1.0
            strip_b.keyframe_insert(data_path='blend_alpha', frame=overlap_end - 1)
            if strip_b.animation_data and strip_b.animation_data.action:
                fcurve = strip_b.animation_data.action.fcurves.find('blend_alpha')
                if fcurve:
                    for kp in fcurve.keyframe_points: kp.interpolation = 'LINEAR'
                    fcurve.update()

        # --- Animación de Zoom In en Clip A ---
        if hasattr(strip_a, 'transform'):
            transform = strip_a.transform
            original_scale_x = transform.scale_x
            original_scale_y = transform.scale_y
            
            zoom_start_frame = round(overlap_start + (overlap_duration * ZOOM_START_PERCENTAGE))

            # Keyframe inicial del zoom (escala original)
            transform.scale_x = original_scale_x # multiplicador de size
            transform.scale_y = original_scale_y # multiplicador de size
            transform.keyframe_insert(data_path='scale_x', frame=zoom_start_frame)
            transform.keyframe_insert(data_path='scale_y', frame=zoom_start_frame)

            # Keyframe final del zoom (con zoom)
            transform.scale_x = original_scale_x * 1.5
            transform.scale_y = original_scale_y * 1.5
            transform.keyframe_insert(data_path='scale_x', frame=overlap_end - 1)
            transform.keyframe_insert(data_path='scale_y', frame=overlap_end - 1)

        osc_feedback.send("/msg", f"PRST {N} OK")

    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error en Preset {N}: {e}")