# Preset 2 Zoom out entrace

"""
PRESET 02: TRANSICIÓN CON ZOOM OUT

- Descripción:
  Aplica un efecto de entrada al segundo clip (Clip B) basado en el
  solapamiento (overlap) con el primer clip (Clip A).
  El Clip B aparece con un fundido y simultáneamente hace un zoom out.

- Requisitos:
  1. Seleccionar exactamente dos strips.
  2. Los strips deben tener un solapamiento de al menos 2 frames.

- Configuración (Hardcoded):
  La variable 'ZOOM_ANIMATION_PERCENTAGE' dentro de este archivo controla
  la duración de la animación del zoom como un porcentaje del overlap total.
  (ej. 0.66 = la animación de zoom dura el 66% del fundido).

- Códigos de Error:
  - E-SEL: Error de Selección. Asegúrate de tener 2 strips seleccionados.
  - E-OVRL: Error de Overlap. Asegúrate de que los strips se solapan
    por al menos 2 frames.
"""

import bpy
from .. import osc_feedback

# --- CONFIGURACIÓN ---
ZOOM_ANIMATION_PERCENTAGE = 0.66

def run(context, *args, **kwargs):
    N = 2

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
        bpy.ops.ed.undo_push(message=f"Preset {N}: Crossfade Zoom")

        # === INICIO DE LA CORRECCIÓN ===
        # --- Animación de Opacidad (Alpha) en Clip A (Fade Out) ---
        if hasattr(strip_a, 'blend_alpha'):
            strip_a.blend_alpha = 1.0
            strip_a.keyframe_insert(data_path='blend_alpha', frame=overlap_start)
            strip_a.blend_alpha = 0.0
            strip_a.keyframe_insert(data_path='blend_alpha', frame=overlap_end - 1)
            
            if strip_a.animation_data and strip_a.animation_data.action:
                fcurve = strip_a.animation_data.action.fcurves.find('blend_alpha')
                if fcurve:
                    for kp in fcurve.keyframe_points:
                        kp.interpolation = 'LINEAR'
                    fcurve.update()
        # === FIN DE LA CORRECCIÓN ===

        # --- Animación de Opacidad (Alpha) en Clip B (Fade In) ---
        if hasattr(strip_b, 'blend_alpha'):
            strip_b.blend_alpha = 0.0
            strip_b.keyframe_insert(data_path='blend_alpha', frame=overlap_start)
            strip_b.blend_alpha = 1.0
            strip_b.keyframe_insert(data_path='blend_alpha', frame=overlap_end - 1)

            if strip_b.animation_data and strip_b.animation_data.action:
                fcurve = strip_b.animation_data.action.fcurves.find('blend_alpha')
                if fcurve:
                    for kp in fcurve.keyframe_points:
                        kp.interpolation = 'LINEAR'
                    fcurve.update()

        # --- Animación de Zoom en Clip B ---
        if hasattr(strip_b, 'transform'):
            transform = strip_b.transform
            original_scale_x = transform.scale_x
            original_scale_y = transform.scale_y
            
            zoom_end_frame = round(overlap_start + (overlap_duration * ZOOM_ANIMATION_PERCENTAGE))

            transform.scale_x = original_scale_x * 1.5 # multiplicador de size
            transform.scale_y = original_scale_y * 1.5 # multiplicador de size
            transform.keyframe_insert(data_path='scale_x', frame=overlap_start)
            transform.keyframe_insert(data_path='scale_y', frame=overlap_start)

            transform.scale_x = original_scale_x
            transform.scale_y = original_scale_y
            transform.keyframe_insert(data_path='scale_x', frame=zoom_end_frame)
            transform.keyframe_insert(data_path='scale_y', frame=zoom_end_frame)
            
        osc_feedback.send("/msg", f"PRST {N} OK")

    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error en Preset {N}: {e}")