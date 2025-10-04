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

# --- CONFIGURACIÓN ---
# Dirección de entrada: puede ser 'LEFT', 'RIGHT', 'TOP', o 'BOTTOM'
SLIDE_DIRECTION = 'RIGHT'

def run(context, *args, **kwargs):
    N = 4

    selected_strips = bpy.context.selected_sequences
    if len(selected_strips) != 2:
        osc_feedback.send("/msg", "E-SEL")
        return

    sorted_strips = sorted(selected_strips, key=lambda s: s.frame_final_start)
    strip_a = sorted_strips[0]
    strip_b = sorted_strips[1]

    if strip_b.channel <= strip_a.channel:
        osc_feedback.send("/msg", "E-CHAN")
        return

    overlap_start = strip_b.frame_final_start
    overlap_end = strip_a.frame_final_end
    overlap_duration = overlap_end - overlap_start

    if overlap_duration < 2:
        osc_feedback.send("/msg", "E-OVRL")
        return

    try:
        bpy.ops.ed.undo_push(message=f"Preset {N}: Slide In")

        if hasattr(strip_b, 'transform'):
            transform = strip_b.transform
            
            # === INICIO DE LA LÓGICA EXTENDIDA ===
            
            # Variable para el data_path del keyframe ('offset_x' o 'offset_y')
            data_path_to_animate = ''
            
            if SLIDE_DIRECTION in {'LEFT', 'RIGHT'}:
                # Lógica para deslizamiento Horizontal
                data_path_to_animate = 'offset_x'
                escala = transform.scale_x
                offset_magnitud = 1.0 + (escala / 2.0)
                offset_inicial = offset_magnitud if SLIDE_DIRECTION == 'RIGHT' else -offset_magnitud
                
                transform.offset_x = offset_inicial
                transform.offset_y = 0.0 # Aseguramos que esté centrado verticalmente

            elif SLIDE_DIRECTION in {'TOP', 'BOTTOM'}:
                # Lógica para deslizamiento Vertical
                data_path_to_animate = 'offset_y'
                escala = transform.scale_y
                offset_magnitud = 1.0 + (escala / 2.0)
                offset_inicial = offset_magnitud if SLIDE_DIRECTION == 'TOP' else -offset_magnitud
                
                transform.offset_y = offset_inicial
                transform.offset_x = 0.0 # Aseguramos que esté centrado horizontalmente
            
            # --- Animación ---
            if data_path_to_animate:
                # 1. Insertar keyframes
                transform.keyframe_insert(data_path=data_path_to_animate, frame=overlap_start)
                
                # Reseteamos el valor correspondiente al centro para el keyframe final
                if data_path_to_animate == 'offset_x':
                    transform.offset_x = 0.0
                else: # offset_y
                    transform.offset_y = 0.0
                
                transform.keyframe_insert(data_path=data_path_to_animate, frame=overlap_end - 1)
                
                # 2. Asegurar interpolación lineal
                if strip_b.animation_data and strip_b.animation_data.action:
                    fcurve = strip_b.animation_data.action.fcurves.find(data_path_to_animate)
                    if fcurve:
                        for kp in fcurve.keyframe_points:
                            kp.interpolation = 'LINEAR'
                        fcurve.update()
            # === FIN DE LA LÓGICA EXTENDIDA ===

        osc_feedback.send("/msg", f"PRST {N} OK")

    except Exception as e:
        osc_feedback.send("/msg", f"E-PRST{N}")
        print(f"Error en Preset {N}: {e}")