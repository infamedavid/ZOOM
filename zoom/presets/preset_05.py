# Preset 5 Slide Out

"""
PRESET 05: SALIDA DESLIZANTE (Slide Out) - 4 DIRECCIONES

- Descripción:
  Crea un efecto de salida para el Clip A, que se desliza desde el centro
  de la pantalla hacia fuera durante el solapamiento con el Clip B.
  No se aplica fundido de opacidad: el clip se mueve físicamente fuera.

- Requisitos:
  1. Seleccionar exactamente dos strips.
  2. El Clip A (el que sale) debe estar en un canal SUPERIOR al Clip B.
  3. Los strips deben tener un solapamiento de al menos 2 frames.

- Configuración (Hardcoded):
  La variable 'SLIDE_DIRECTION' controla la dirección de salida.
  Valores posibles: 'LEFT', 'RIGHT', 'TOP', 'BOTTOM'.

- Códigos de Error:
  - E-SEL: Error de Selección (deben estar seleccionados 2 strips).
  - E-OVRL: Error de Overlap (no hay solapamiento suficiente).
  - E-CHAN: Error de Canal (el Clip A no está en un canal superior).
"""

import bpy
from .. import osc_feedback

SLIDE_DIRECTION = 'RIGHT'
SLIDE_DISTANCE_FACTOR = 1.0
SLIDE_MARGIN_PX = 64

def _set_linear_interpolation(strip_name, path, frames):
    anim = bpy.context.scene.animation_data
    if anim and anim.action:
        fcurve = anim.action.fcurves.find(
            f'sequence_editor.sequences_all["{strip_name}"].{path}'
        )
        if fcurve:
            for kp in fcurve.keyframe_points:
                if frames is None or int(kp.co.x) in frames:
                    kp.interpolation = 'LINEAR'
            fcurve.update()

def _scene_pixels(scene):
    r = scene.render
    px_w = r.resolution_x * (r.resolution_percentage / 100.0)
    px_h = r.resolution_y * (r.resolution_percentage / 100.0)
    return float(px_w), float(px_h)

def _strip_orig_size(strip):
    try:
        if getattr(strip, "elements", None):
            elem = strip.elements[0]
            w = getattr(elem, "orig_width", None)
            h = getattr(elem, "orig_height", None)
            if w and h:
                return float(w), float(h)
    except Exception:
        pass
    return None, None

def run(context, *args, **kwargs):
    N = 5
    selected = bpy.context.selected_sequences
    if len(selected) != 2:
        osc_feedback.send("/msg", "E-SEL"); return

    sorted_strips = sorted(selected, key=lambda s: s.frame_final_start)
    strip_a, strip_b = sorted_strips[0], sorted_strips[1]

    # Ahora el que sale es A, y debe estar ARRIBA de B
    if strip_a.channel <= strip_b.channel:
        osc_feedback.send("/msg", "E-CHAN"); return

    overlap_start, overlap_end = strip_b.frame_final_start, strip_a.frame_final_end
    if (overlap_end - overlap_start) < 2:
        osc_feedback.send("/msg", "E-OVRL"); return

    try:
        bpy.ops.ed.undo_push(message=f"Preset {N}: Slide Out")

        if not hasattr(strip_a, 'transform'):
            osc_feedback.send("/msg", f"E-PRST{N}: no transform"); return

        transform = strip_a.transform
        scene = bpy.context.scene

        scene_w_px, scene_h_px = _scene_pixels(scene)
        orig_w, orig_h = _strip_orig_size(strip_a)

        scale_x = getattr(transform, "scale_x", 1.0) or 1.0
        scale_y = getattr(transform, "scale_y", 1.0) or 1.0

        if orig_w and orig_h:
            scaled_w_px = orig_w * scale_x
            scaled_h_px = orig_h * scale_y
        else:
            scaled_w_px = scene_w_px * scale_x
            scaled_h_px = scene_h_px * scale_y

        # cálculo del offset de salida
        if SLIDE_DIRECTION in {'LEFT', 'RIGHT'}:
            base_offset_px = (scene_w_px / 2.0) + (scaled_w_px / 2.0) + SLIDE_MARGIN_PX
            offset_px = base_offset_px * (SLIDE_DISTANCE_FACTOR or 1.0)
            offset_value = -offset_px if SLIDE_DIRECTION == 'LEFT' else offset_px
            path_to_animate = 'offset_x'
        else:
            base_offset_px = (scene_h_px / 2.0) + (scaled_h_px / 2.0) + SLIDE_MARGIN_PX
            offset_px = base_offset_px * (SLIDE_DISTANCE_FACTOR or 1.0)
            offset_value = -offset_px if SLIDE_DIRECTION == 'BOTTOM' else offset_px
            path_to_animate = 'offset_y'

        # Keyframes: empieza centrado, termina fuera
        setattr(transform, path_to_animate, 0.0)
        transform.keyframe_insert(data_path=path_to_animate, frame=overlap_start)

        setattr(transform, path_to_animate, offset_value)
        transform.keyframe_insert(data_path=path_to_animate, frame=overlap_end - 1)

        bpy.context.view_layer.update()
        _set_linear_interpolation(strip_a.name, f"transform.{path_to_animate}", [overlap_start, overlap_end - 1])

        osc_feedback.send("/msg", f"PRST {N} OK salida {SLIDE_DIRECTION} ({offset_value:.1f}px)")

    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error general en Preset {N}: {e}")