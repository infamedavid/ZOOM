# Preset 2 Slide in

"""
PRESET 04: ENTRADA DESLIZANTE (Slide In) - 4 DIRECCIONES

- Descripción:
  Crea un efecto de entrada para el Clip B, que se desliza desde fuera
  de la pantalla hasta el centro durante el solapamiento (overlap) con
  el Clip A. No se aplica ningún fundido de opacidad.

- Requisitos:
  1. Seleccionar exactamente dos strips.
  2. El Clip B (el que entra) debe estar en un canal SUPERIOR al Clip A.
  3. Los strips deben tener un solapamiento de al menos 2 frames.

- Configuración (Hardcoded):
  La variable 'SLIDE_DIRECTION' controla la dirección de entrada.
  Valores posibles: 'LEFT', 'RIGHT', 'TOP', 'BOTTOM'.

- Códigos de Error:
  - E-SEL: Error de Selección.
  - E-OVRL: Error de Overlap.
  - E-CHAN: Error de Canal (El Clip B no está en un canal superior).
"""

import bpy
from .. import osc_feedback

# Configuración -- ajústalas si quieres
SLIDE_DIRECTION = 'RIGHT'          # 'LEFT' | 'RIGHT' | 'TOP' | 'BOTTOM'
SLIDE_DISTANCE_FACTOR = 1.0        # multiplicador extra para asegurar que quede fuera
SLIDE_MARGIN_PX = 64               # margen extra en píxeles

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
    """
    Intenta devolver (orig_width, orig_height) en píxeles.
    Si no encuentra metadata, devuelve (None, None).
    """
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
    N = 4
    selected = bpy.context.selected_sequences
    if len(selected) != 2:
        osc_feedback.send("/msg", "E-SEL"); return

    sorted_strips = sorted(selected, key=lambda s: s.frame_final_start)
    strip_a, strip_b = sorted_strips[0], sorted_strips[1]

    if strip_b.channel <= strip_a.channel:
        osc_feedback.send("/msg", "E-CHAN"); return

    overlap_start, overlap_end = strip_b.frame_final_start, strip_a.frame_final_end
    if (overlap_end - overlap_start) < 2:
        osc_feedback.send("/msg", "E-OVRL"); return

    try:
        bpy.ops.ed.undo_push(message=f"Preset {N}: Slide In (pixel offset)")

        if not hasattr(strip_b, 'transform'):
            osc_feedback.send("/msg", f"E-PRST{N}: no transform"); return

        transform = strip_b.transform
        scene = bpy.context.scene

        # --- scene pixels ---
        scene_w_px, scene_h_px = _scene_pixels(scene)

        # --- strip original size (px) ---
        orig_w, orig_h = _strip_orig_size(strip_b)

        # --- scale (transform.scale_x/y) ---
        scale_x = getattr(transform, "scale_x", 1.0) or 1.0
        scale_y = getattr(transform, "scale_y", 1.0) or 1.0

        # --- compute scaled strip size in px (fallback to scene size if no orig) ---
        if orig_w and orig_h:
            scaled_w_px = orig_w * scale_x
            scaled_h_px = orig_h * scale_y
        else:
            # fallback conservador: asumimos que el strip "cubre" el frame a escala 1.0
            scaled_w_px = scene_w_px * scale_x
            scaled_h_px = scene_h_px * scale_y

        # --- compute required offset in pixels ---
        if SLIDE_DIRECTION in {'LEFT', 'RIGHT'}:
            base_offset_px = (scene_w_px / 2.0) + (scaled_w_px / 2.0) + SLIDE_MARGIN_PX
            offset_px = base_offset_px * (SLIDE_DISTANCE_FACTOR or 1.0)
            if SLIDE_DIRECTION == 'LEFT':
                offset_value = -offset_px
            else:
                offset_value = offset_px
            path_to_animate = 'offset_x'
        else:
            base_offset_px = (scene_h_px / 2.0) + (scaled_h_px / 2.0) + SLIDE_MARGIN_PX
            offset_px = base_offset_px * (SLIDE_DISTANCE_FACTOR or 1.0)
            if SLIDE_DIRECTION == 'BOTTOM':
                offset_value = -offset_px
            else:
                offset_value = offset_px
            path_to_animate = 'offset_y'

        # --- insert keyframes (valor en unidades EXPECTED por transform.offset_*) ---
        # Nota: asumimos que transform.offset_x/y usan las mismas unidades que los píxeles del proyecto.
        # Si tu versión de Blender usa otra unidad, ajusta SLIDE_DISTANCE_FACTOR o convierte aquí.
        setattr(transform, path_to_animate, offset_value)
        transform.keyframe_insert(data_path=path_to_animate, frame=overlap_start)

        setattr(transform, path_to_animate, 0.0)
        transform.keyframe_insert(data_path=path_to_animate, frame=overlap_end - 1)

        bpy.context.view_layer.update()

        # --- forzar interpolación LINEAL en las dos claves ---
        _set_linear_interpolation(strip_b.name, f"transform.{path_to_animate}", [overlap_start, overlap_end - 1])

        # --- feedback debug --- (te informa px calculados)
        osc_feedback.send("/msg", f"PRST {N} OK off={offset_value:.1f}px (scene {scene_w_px:.0f}x{scene_h_px:.0f}, strip {scaled_w_px:.0f}x{scaled_h_px:.0f})")

    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error general en Preset {N}: {e}")