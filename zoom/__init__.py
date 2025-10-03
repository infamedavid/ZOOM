import bpy
import importlib
from bpy.app.handlers import persistent

from . import state
from . import osc_server
from . import transport_extra
from . import strips_extra
from . import tools_extra 
from . import adds
from . import adds_fx
from . import tools_fx
from . import strips_tools
from . import osc_feedback
from . import strips_advance
from . import groups_logic
from . import offsets_tools
from . import fades
from . import bl_cam
from . import bl_cam_prop
from . import bl_cam_optics
from . import audio_internal
from . import quicks
from . import exports
from . import channels
from . import modifiers
from . import markers
from . import simple_commands
from . import preferences
from . import macros

if "bpy" in locals():
    importlib.reload(state)
    importlib.reload(osc_server)
    importlib.reload(transport_extra)
    importlib.reload(strips_extra)
    importlib.reload(tools_extra)
    importlib.reload(adds)
    importlib.reload(adds_fx)
    importlib.reload(tools_fx)
    importlib.reload(strips_tools)
    importlib.reload(osc_feedback)
    importlib.reload(strips_advance)
    importlib.reload(groups_logic)
    importlib.reload(offsets_tools)
    importlib.reload(fades)
    importlib.reload(bl_cam)
    importlib.reload(bl_cam_prop)
    importlib.reload(bl_cam_optics)
    importlib.reload(audio_internal)
    importlib.reload(quicks)
    importlib.reload(exports)
    importlib.reload(channels)
    importlib.reload(modifiers)
    importlib.reload(markers)
    importlib.reload(simple_commands)
    importlib.reload(preferences)
    importlib.reload(macros)

bl_info = {
    "name": "ZOOM",
    "author": "Infame",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Video Sequence Editor > N-Panel > OSC VSE",
    "description": "Control Surface for the Blender Video Sequence Editor using OSC protocol",
    "category": "Sequencer",
}

_modules = [
    osc_server,
    transport_extra,
    strips_extra,
    tools_extra,
    adds,
    adds_fx,
    tools_fx,
    strips_tools,
    osc_feedback,
    strips_advance,
    groups_logic,
    offsets_tools,
    fades,
    bl_cam,
    bl_cam_prop,
    bl_cam_optics,
    audio_internal,
    quicks,
    exports,
    channels,
    modifiers,
    markers,
    simple_commands,
    preferences,
    macros,  # <-- añadido para consistencia
]

@persistent
def on_load_init_groups(dummy):
    groups_logic.init_group_system()

def register():
    for module in _modules:
        if hasattr(module, 'register'):
            module.register()
            
    for module in _modules:
        if hasattr(module, 'register_actions'):
            module.register_actions()

    # Handlers globales
    if strips_extra.sync_selection_set_with_scene not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(strips_extra.sync_selection_set_with_scene)
    if osc_feedback.timecode_frame_change_handler not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(osc_feedback.timecode_frame_change_handler)
    if on_load_init_groups not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_init_groups)

    # Handlers multicam (resync undo/save)
    try:
        bl_cam.register_handlers()
    except Exception as e:
        print("Error registrando handlers de bl_cam:", e)

    # Descubrir presets de macros dinámicos
    try:
        macros.discover_presets()
    except Exception as e:
        print(f"[__init__] Error discover_presets: {e}")

    print(f"{bl_info['name']} (v{bl_info['version'][0]}.{bl_info['version'][1]}) registered.")

def unregister():
    if strips_extra.sync_selection_set_with_scene in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(strips_extra.sync_selection_set_with_scene)
    if osc_feedback.timecode_frame_change_handler in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(osc_feedback.timecode_frame_change_handler)
    if on_load_init_groups in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_init_groups)

    # Handlers multicam
    try:
        bl_cam.unregister_handlers()
    except Exception as e:
        print("Error desregistrando handlers de bl_cam:", e)

    for module in reversed(_modules):
        if hasattr(module, 'unregister'):
            module.unregister()
            
    if hasattr(state, 'plus_minus_actions'):
        state.plus_minus_actions.clear()
    if hasattr(state, 'jog_actions'):
        state.jog_actions.clear()
    if hasattr(state, 'tool_specific_actions'):
        state.tool_specific_actions.clear()

    # Limpiar cache de macros
    try:
        if hasattr(macros, "_loaded_presets"):
            macros._loaded_presets.clear()
    except Exception:
        pass

    print(f"{bl_info['name']} unregistered.")
