# adds.py

import bpy
from . import state
from . import groups_logic

# Diccionario para mapear direcciones OSC a los operadores de Blender
_add_operator_map = {
    "/add_movie": "sequencer.movie_strip_add",
    "/add_image": "sequencer.image_strip_add",
    "/add_imseq": "sequencer.image_strip_add", # Usa el mismo operador que add_image
    "/add_audio": "sequencer.sound_strip_add",
    "/add_scene": "sequencer.scene_strip_add",
    "/add_text": "sequencer.effect_strip_add",
    "/add_color": "sequencer.effect_strip_add",
    "/add_adjust": "sequencer.effect_strip_add",
    "/add_marker": "marker.add",
}

# Kwargs para operadores que necesitan parámetros específicos
_add_operator_kwargs = {
    "/add_text": {'type': 'TEXT'},
    "/add_color": {'type': 'COLOR'},
    "/add_adjust": {'type': 'ADJUSTMENT'},
}


def get_sequencer_context():
    """
    Busca un área del 'SEQUENCE_EDITOR' visible y devuelve un contexto
    anulado (override context) completo para que los operadores funcionen.
    """
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override_context = {
                            'window': window,
                            'screen': window.screen,
                            'area': area,
                            'region': region,
                            'space_data': area.spaces.active,
                        }
                        return override_context
    return None


def handle_add_generic(address, args):
    """
    Manejador para añadir strips que requieren el explorador de archivos.
    """
    if not args or not args[0]:
        return

    override_context = get_sequencer_context()
    if override_context is None:
        print("OSC VSE Error: No se encontró un área de 'Video Sequence Editor' visible. No se puede añadir el strip.")
        return

    operator_str = _add_operator_map.get(address)
    if not operator_str:
        print(f"OSC VSE Warning: No se encontró un operador para la dirección '{address}'")
        return

    # --- AÑADIDO: Punto de Undo ---
    action_name = address.split('_')[-1].capitalize()
    bpy.ops.ed.undo_push(message=f"OSC Add {action_name}")

    module_name, op_name = operator_str.split('.')
    operator = getattr(getattr(bpy.ops, module_name), op_name)

    kwargs = _add_operator_kwargs.get(address, {})

    # Guardamos strips antes de añadir
    scene = bpy.context.scene
    seq_before = set(s.name for s in scene.sequence_editor.sequences_all) if scene and scene.sequence_editor else set()

    try:
        with bpy.context.temp_override(**override_context):
            if address == '/add_imseq':
                operator('INVOKE_DEFAULT', files=[], directory="", relative_path=True)
            else:
                operator('INVOKE_DEFAULT', **kwargs)
    except Exception as e:
        print(f"OSC VSE Error: No se pudo ejecutar el operador '{operator_str}': {e}")
        return

    # --- AUTO MIRROR HOOK: agrupar strips recién nacidos ---
    if state.control_state.get("auto_mirror", False) and scene and scene.sequence_editor:
        seq_after = set(s.name for s in scene.sequence_editor.sequences_all)
        new_names = seq_after - seq_before
        new_strips = [s for s in scene.sequence_editor.sequences_all if s.name in new_names]
        if new_strips:
            try:
                groups_logic.auto_mirror_birth(new_strips)
            except Exception as e:
                print(f"AUTO MIRROR: error en auto_mirror_birth (adds): {e}")


def handle_create_meta(address, args):
    """
    Manejador contextual para Meta Strips.
    - Si se selecciona un Meta Strip, lo desagrupa (un-meta) usando meta_separate.
    - Si se seleccionan varios strips, los agrupa en un Meta Strip.
    """
    if not args or not args[0]: return # <-- CORRECCIÓN: Añadido para seguir el patrón del resto de handlers

    selected = bpy.context.selected_sequences
    if not selected:
        return

    context = get_sequencer_context()
    if not context:
        print("OSC VSE Error: No se encontró un área de 'Video Sequence Editor' visible.")
        return

    # --- Lógica de Toggle Corregida ---
    # Caso 1: Desagrupar un Meta Strip si solo hay uno seleccionado.
    if len(selected) == 1 and selected[0].type == 'META':
        bpy.ops.ed.undo_push(message="OSC Un-Meta Strip")
        try:
            with bpy.context.temp_override(**context):
                # <-- CORRECCIÓN: Usar meta_separate en lugar de meta_toggle
                bpy.ops.sequencer.meta_separate()
            osc_feedback.send_action_feedback("UN-META")
        except Exception as e:
            print(f"OSC VSE Error: No se pudo desagrupar el meta strip: {e}")

    # Caso 2: Crear un Meta Strip si hay uno o más strips seleccionados
    elif len(selected) >= 1:
        bpy.ops.ed.undo_push(message="OSC Add Meta Strip")
        try:
            with bpy.context.temp_override(**context):
                bpy.ops.sequencer.meta_make()
            osc_feedback.send_action_feedback("META ADDED")
        except Exception as e:
            print(f"OSC VSE Error: No se pudo crear el meta strip: {e}")


def register():
    """Función de registro para este módulo."""
    pass

def unregister():
    """Función de anulación de registro para este módulo."""
    pass