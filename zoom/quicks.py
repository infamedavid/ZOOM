# quicks.py

import bpy
from . import state
from . import osc_feedback

# --- Funciones Auxiliares de Búsqueda ---

def _find_single_relative_strip(reference_strip, all_strips, direction, use_type_filter, use_channel_filter, exclude_list):
    """
    Motor de búsqueda para encontrar un único strip relativo a una referencia.
    """
    candidates = [s for s in all_strips if s.name not in exclude_list]

    # Aplicar filtros
    if use_type_filter:
        candidates = [s for s in candidates if s.type == reference_strip.type]
    if use_channel_filter:
        candidates = [s for s in candidates if s.channel == reference_strip.channel]
    
    if not candidates:
        return None

    # Ordenar por frame de inicio
    sorted_candidates = sorted(candidates, key=lambda s: s.frame_final_start)
    
    # Encontrar el objetivo
    target_strip = None
    if direction == 1: # Siguiente
        for s in sorted_candidates:
            if s.frame_final_start > reference_strip.frame_final_start:
                target_strip = s
                break
    else: # Anterior
        for s in reversed(sorted_candidates):
            if s.frame_final_start < reference_strip.frame_final_start:
                target_strip = s
                break
    
    return target_strip

def _find_relative_strips(selection, direction):
    """
    Función principal que decide cómo buscar y devuelve una lista de strips para la nueva selección.
    """
    selection_count = len(selection)
    all_strips = list(bpy.context.scene.sequence_editor.sequences_all)
    exclude_names = {s.name for s in selection}
    new_selection = []

    # Determinar las reglas de filtrado según las normas acordadas
    use_type_filter = state.control_state.get('quick_select_type_lock', True)
    use_channel_filter = state.control_state.get('quick_select_channel_lock', False)

    if selection_count == 1:
        # CASO 1: Un solo strip seleccionado. Se respetan los filtros del usuario.
        reference_strip = selection[0]
        found = _find_single_relative_strip(reference_strip, all_strips, direction, use_type_filter, use_channel_filter, exclude_names)
        if found:
            new_selection.append(found)

    elif selection_count > 1:
        # CASO 2: Múltiples strips. Se fuerza el filtro de tipo.
        use_type_filter = True # Forzar filtro de tipo
        
        # Enviar feedback a la superficie para que el usuario vea que el filtro se ha activado
        osc_feedback.send("/quick_type_lock/state", True)
        # También actualizamos el estado interno para mantener la consistencia
        state.control_state['quick_select_type_lock'] = True

        for reference_strip in selection:
            found = _find_single_relative_strip(reference_strip, all_strips, direction, use_type_filter, use_channel_filter, exclude_names)
            if found:
                new_selection.append(found)
                
    return new_selection

# --- Manejadores de Comandos OSC ---

def handle_quick_select(address, args):
    """Maneja /quick_select_next y /quick_select_prev."""
    if not args or not args[0]: return # Ejecutar solo al presionar
    
    direction = 1 if address == "/quick_select_next" else -1
    selected_strips = bpy.context.selected_sequences
    
    if not selected_strips:
        return

    bpy.ops.ed.undo_push(message="OSC Quick Select")

    strips_to_select = _find_relative_strips(selected_strips, direction)

    if strips_to_select:
        bpy.ops.sequencer.select_all(action='DESELECT')
        for strip in strips_to_select:
            strip.select = True
        
        # Asegurarse de que uno de los nuevos strips sea el activo
        bpy.context.scene.sequence_editor.active_strip = strips_to_select[0]

def handle_quick_delete(address, args):
    """Maneja el borrado inteligente."""
    if not args or not args[0]: return

    selection_before_delete = bpy.context.selected_sequences
    if not selection_before_delete:
        return

    bpy.ops.ed.undo_push(message="OSC Quick Delete")
    
    # Prioridad 1: Buscar candidatos anteriores del mismo tipo
    # Para ello, usamos nuestra función de búsqueda, forzando el filtro de tipo.
    # Creamos una selección "falsa" para que la función opere sobre ella.
    strips_to_select = []
    all_strips = list(bpy.context.scene.sequence_editor.sequences_all)
    exclude_names = {s.name for s in selection_before_delete}

    for strip in selection_before_delete:
        found = _find_single_relative_strip(strip, all_strips, -1, True, False, exclude_names)
        if found:
            strips_to_select.append(found)

    # Prioridad 2 (Fallback): Si no hay anteriores, buscar siguientes
    if not strips_to_select:
        for strip in selection_before_delete:
            found = _find_single_relative_strip(strip, all_strips, 1, True, False, exclude_names)
            if found:
                strips_to_select.append(found)

    # Ejecutar el borrado
    bpy.ops.sequencer.delete()

    # Aplicar la nueva selección
    if strips_to_select:
        for strip in strips_to_select:
            # El strip podría haber sido borrado si era un efecto del principal
            if strip.name in bpy.context.scene.sequence_editor.sequences_all:
                strip.select = True
        
        bpy.context.scene.sequence_editor.active_strip = strips_to_select[0]

def handle_filter_toggle(address, args):
    """Maneja los toggles de los filtros."""
    if not args or not isinstance(args[0], bool):
        return

    new_state = args[0]
    if address == "/quick_type_lock":
        state.control_state['quick_select_type_lock'] = new_state
        print(f"OSC Quick Select: Filtro de Tipo {'ACTIVADO' if new_state else 'DESACTIVADO'}")
    elif address == "/quick_channel_lock":
        state.control_state['quick_select_channel_lock'] = new_state
        print(f"OSC Quick Select: Filtro de Canal {'ACTIVADO' if new_state else 'DESACTIVADO'}")

def register():
    # Inicializar los estados de los filtros si no existen
    state.control_state.setdefault('quick_select_type_lock', True)
    state.control_state.setdefault('quick_select_channel_lock', False)

def unregister():
    pass