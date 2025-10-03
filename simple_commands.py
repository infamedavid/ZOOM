# simple_commands.py

import bpy
import os
from . import osc_feedback

def _get_sequencer_context():
    """
    Busca un área del 'SEQUENCE_EDITOR' visible y devuelve un contexto
    anulado (override context) para que los operadores funcionen.
    Es una copia local para evitar dependencias externas.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {
                            'window': window,
                            'screen': window.screen,
                            'area': area,
                            'region': region,
                            'space_data': area.spaces.active,
                        }
    print("OSC SimpleCmds Error: No se encontró un área de 'Video Sequence Editor' visible.")
    return None

# --- Handlers para Undo/Redo ---

def handle_undo(address, args):
    """Manejador para la operación Deshacer."""
    if not args or not args[0]: return
    try:
        bpy.ops.ed.undo()
        osc_feedback.send_action_feedback("UNDO")
    except Exception as e:
        print(f"OSC Error en Undo: {e}")

def handle_redo(address, args):
    """Manejador para la operación Rehacer."""
    if not args or not args[0]: return
    try:
        bpy.ops.ed.redo()
        osc_feedback.send_action_feedback("REDO")
    except Exception as e:
        print(f"OSC Error en Redo: {e}")

# --- Handlers para Copy/Paste/Duplicate ---

def handle_copy(address, args):
    """Manejador para copiar strips seleccionados."""
    if not args or not args[0]: return
    context = _get_sequencer_context()
    if not context: return
    try:
        with bpy.context.temp_override(**context):
            bpy.ops.sequencer.copy()
        osc_feedback.send_action_feedback("COPIED")
    except Exception as e:
        print(f"OSC Error en Copy: {e}")

def handle_paste(address, args):
    """Manejador para pegar strips en el cursor."""
    if not args or not args[0]: return
    context = _get_sequencer_context()
    if not context: return
    try:
        with bpy.context.temp_override(**context):
            bpy.ops.sequencer.paste(keep_offset=True)
        osc_feedback.send_action_feedback("PASTED")
    except Exception as e:
        print(f"OSC Error en Paste: {e}")

def handle_duplicate(address, args):
    """Manejador para duplicar strips seleccionados."""
    if not args or not args[0]: return
    context = _get_sequencer_context()
    if not context: return
    try:
        with bpy.context.temp_override(**context):
            bpy.ops.sequencer.duplicate_move('INVOKE_DEFAULT', dup_linked=False)
        osc_feedback.send_action_feedback("DUPLICATED")
    except Exception as e:
        print(f"OSC Error en Duplicate: {e}")

# --- Handlers para Toggle Mute/Lock ---

def handle_toggle_mute(address, args):
    """Alterna el estado Mute de los strips seleccionados."""
    if not args or not args[0]: return
    
    selected = bpy.context.selected_sequences
    if not selected: return

    # Determinar el nuevo estado basado en el strip activo
    active_strip = bpy.context.scene.sequence_editor.active_strip
    if not active_strip or active_strip not in selected:
        active_strip = selected[0]
        
    new_state = not active_strip.mute
    
    for strip in selected:
        strip.mute = new_state
        
    feedback_msg = "MUTED" if new_state else "UNMUTED"
    osc_feedback.send_action_feedback(feedback_msg)

def handle_toggle_lock(address, args):
    """Alterna el estado Lock de los strips seleccionados."""
    if not args or not args[0]: return

    selected = bpy.context.selected_sequences
    if not selected: return

    active_strip = bpy.context.scene.sequence_editor.active_strip
    if not active_strip or active_strip not in selected:
        active_strip = selected[0]

    new_state = not active_strip.lock
    
    for strip in selected:
        strip.lock = new_state

    feedback_msg = "LOCKED" if new_state else "UNLOCKED"
    osc_feedback.send_action_feedback(feedback_msg)

def handle_save(address, args):
    """
    Guarda el archivo .blend actual. Si no ha sido guardado,
    abre el explorador de archivos, como es el comportamiento nativo.
    """
    if not args or not args[0]:
        return
    
    try:
        bpy.ops.wm.save_mainfile()
        osc_feedback.send_action_feedback("SAVED")
    except Exception as e:
        print(f"OSC Save Error: {e}")
        osc_feedback.send_action_feedback("SAVE ERROR")

def handle_save_incremental(address, args):
    """
    Guarda una nueva versión del archivo .blend, incrementando
    el número en el nombre del archivo.
    """
    if not args or not args[0]:
        return
        
    try:
        # Guardamos la ruta actual para compararla después
        old_filepath = bpy.data.filepath
        
        bpy.ops.wm.save_mainfile(increment=True)
        
        new_filepath = bpy.data.filepath
        
        # Si la ruta cambió, significa que el guardado incremental fue exitoso
        if new_filepath != old_filepath:
            new_filename = os.path.basename(new_filepath)
            # Extraemos la parte final del nombre para un feedback más corto
            feedback_msg = f"SAVED {new_filename.replace('.blend', '')[-4:]}"
            osc_feedback.send_action_feedback(feedback_msg)
        else:
            # Esto puede pasar en la primera guardada, donde se abre el browser
            osc_feedback.send_action_feedback("SAVED AS")
            
    except Exception as e:
        print(f"OSC Save Incremental Error: {e}")
        osc_feedback.send_action_feedback("SAVE ERROR")
    

def handle_edit_meta(address, args):
    """Entra o sale de un Meta Strip usando meta_toggle."""
    if not args or not args[0]:
        return

    context = _get_sequencer_context()
    if not context:
        print("OSC Edit Meta Error: No se encontró un área SEQUENCE_EDITOR.")
        return

    try:
        bpy.ops.ed.undo_push(message="OSC Meta Toggle")
        with bpy.context.temp_override(**context):
            bpy.ops.sequencer.meta_toggle()
        osc_feedback.send_action_feedback("META EDIT TOGGLE")
    except Exception as e:
        print(f"OSC Edit Meta Error: {e}")

def handle_set_start(address, args):
    """Fija el frame actual como inicio de la línea de tiempo."""
    if not args or not args[0]:
        return

    try:
        scene = bpy.context.scene
        bpy.ops.ed.undo_push(message="OSC Set Start Frame")
        scene.frame_start = scene.frame_current
        osc_feedback.send_action_feedback("START SET")
    except Exception as e:
        print(f"OSC Error en Set Start: {e}")


def handle_set_end(address, args):
    """Fija el frame actual como final de la línea de tiempo."""
    if not args or not args[0]:
        return

    try:
        scene = bpy.context.scene
        bpy.ops.ed.undo_push(message="OSC Set End Frame")
        scene.frame_end = scene.frame_current
        osc_feedback.send_action_feedback("END SET")
    except Exception as e:
        print(f"OSC Error en Set End: {e}")
