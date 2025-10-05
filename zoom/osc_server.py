# osc_server.py

import bpy
import threading
import socket
from pythonosc import dispatcher
from pythonosc import osc_server
import functools
from bpy.app.handlers import persistent
from . import state
from . import transport_extra
from . import strips_extra
from . import tools_extra 
from . import adds
from . import adds_fx
from . import tools_fx
from . import strips_tools
from . import strips_advance
from . import groups_logic
from . import offsets_tools
from . import fades
from . import bl_cam
from . import bl_cam_prop
from . import osc_feedback
from . import bl_cam_optics
from . import audio_internal
from . import quicks
from . import exports
from . import channels
from . import modifiers
from . import markers
from . import simple_commands
from . import macros 

# --- Obtener IP -----

def _get_local_ip():
    """
    Encuentra la dirección IP local de la máquina en la red.
    """
    s = None
    try:
        # Crea un socket UDP temporal
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Conecta a una IP pública (no se envía tráfico real)
        s.connect(("8.8.8.8", 80))
        # Obtiene la IP que el sistema usaría para esta conexión
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"  
    finally:
        if s:
            s.close()
    return ip

# ---  MONITOR DE ESTADO ---

def monitor_addon_state():
    """
    Timer que comprueba periódicamente si el estado real de la herramienta
    activa en Blender coincide con el último estado enviado por feedback.
    Si no coincide, fuerza una actualización.
    """
    current_tool_name = "        " 
    
    custom_name = state.control_state.get('active_tool_custom_name')
    if custom_name:
        current_tool_name = custom_name
    elif state.control_state.get('strip_nav_active', False):
        current_tool_name = osc_feedback.TOOL_NAME_MAP.get("navigate", "STRIP SEL")
    else:
        active_tools = state.control_state.get('active_tools', set())
        if active_tools:
            internal_name = next(iter(active_tools))
            current_tool_name = osc_feedback.TOOL_NAME_MAP.get(internal_name, internal_name.upper())

    if current_tool_name != state.control_state.get('last_sent_tool'):
        print(f"State Monitor: Desync detected! State is '{current_tool_name}', last sent was '{state.control_state.get('last_sent_tool')}'. Forcing feedback.")
        osc_feedback.send_active_tool_feedback()
    
    return 0.5 # Intervalo de comprobación en segundos

def start_state_monitor():
    if not bpy.app.timers.is_registered(monitor_addon_state):
        state.control_state['state_monitor_timer'] = bpy.app.timers.register(monitor_addon_state)
        print("OSC VSE: State Monitor ACTIVADO.")

def stop_state_monitor():
    timer = state.control_state.get('state_monitor_timer')
    if timer and bpy.app.timers.is_registered(monitor_addon_state):
        bpy.app.timers.unregister(timer)
    state.control_state['state_monitor_timer'] = None
    print("OSC VSE: State Monitor DESACTIVADO.")


@persistent
def on_load_reset_server_state(dummy):
    server_thread_info.update({"server": None, "thread": None})
    if hasattr(bpy.context.scene, "osc_vse_properties"):
        bpy.context.scene.osc_vse_properties.is_server_running = False
    print("OSC VSE server state has been reset on file load.")

class OSCVSEProperties(bpy.types.PropertyGroup):
    ip: bpy.props.StringProperty(name="IP Address", default="0.0.0.0")
    port: bpy.props.IntProperty(name="Port", default=8000, min=1, max=65535)
    is_server_running: bpy.props.BoolProperty(name="Is Server Running", default=False)
    detected_ip: bpy.props.StringProperty(name="Server Address", default="N/A (server stopped)")
    client_ip: bpy.props.StringProperty(name="Client IP", description="IP address of the OSC control surface", default="127.0.0.1")
    client_port: bpy.props.IntProperty(name="Client Port", description="Port of the OSC control surface", default=8001, min=1, max=65535)
    max_scrub_speed: bpy.props.FloatProperty(name="Max Scrub Speed", default=16.0, min=6.0, max=128.0)
    min_scrub_speed: bpy.props.FloatProperty(name="Min Scrub Speed", default=2.0, min=0.0, max=6.0)
    jog_tool_intensity: bpy.props.FloatProperty(name="Jog Tool Intensity", default=1.0, min=0.2, max=5.0)
    jog_relative_speed_divisor: bpy.props.FloatProperty(name="Divisor de Velocidad Relativa", default=20.0, min=1.0, max=500.0)
    zoom_snap_value: bpy.props.FloatProperty(name="Snap de Zoom", default=1.0, min=0.01)
    position_x_snap_value: bpy.props.FloatProperty(name="Snap de Posición X", default=0.0)
    position_y_snap_value: bpy.props.FloatProperty(name="Snap de Posición Y", default=0.0)
    rotation_snap_value: bpy.props.FloatProperty(name="Snap de Rotación", default=0.0)
    origin_x_snap_value: bpy.props.FloatProperty(name="Snap de Origen X", default=0.0)
    origin_y_snap_value: bpy.props.FloatProperty(name="Snap de Origen Y", default=0.0)
    grab_user_speed: bpy.props.FloatProperty(
        name="Velocidad de Arrastre (Grab)",
        description="Multiplicador de velocidad para la herramienta de arrastre de strips",
        default=5.0,
        min=1.0,
        max=10.0
    )
    show_filters_box: bpy.props.BoolProperty(name="Mostrar filtros", default=True)
    filter_movie: bpy.props.BoolProperty(name="Películas (Movie)", default=True)
    filter_image: bpy.props.BoolProperty(name="Imágenes", default=True)
    filter_meta: bpy.props.BoolProperty(name="Meta Strips", default=True)
    filter_audio: bpy.props.BoolProperty(name="Audio", default=True)
    filter_color: bpy.props.BoolProperty(name="Color", default=False)
    filter_text: bpy.props.BoolProperty(name="Texto", default=False)
    filter_adjustment: bpy.props.BoolProperty(name="Capa de Ajuste", default=False)
    filter_effect_speed: bpy.props.BoolProperty(name="Control de Velocidad", default=False)
    filter_effect_transform: bpy.props.BoolProperty(name="Transformación", default=False)
    filter_transitions: bpy.props.BoolProperty(name="Transiciones", default=False)
    filter_scene: bpy.props.BoolProperty(name="Escenas", default=False)
    filter_clip: bpy.props.BoolProperty(name="Clips", default=False)
    filter_mask: bpy.props.BoolProperty(name="Máscaras", default=False)
    filter_glow: bpy.props.BoolProperty(name="Glow",default=True,)
    filter_blur: bpy.props.BoolProperty(name="Gaussian Blur",default=True,)

class UI_UL_osc_presets(bpy.types.UIList):
    """Define cómo se dibuja la lista de presets."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "name", text="", emboss=False, icon='NETWORK_DRIVE')
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='NETWORK_DRIVE')

class WM_OT_osc_preset_actions(bpy.types.Operator):
    """Operador para Añadir y Eliminar presets de la lista."""
    bl_idname = "zoom.preset_actions"
    bl_label = "OSC Preset Actions"
    
    action: bpy.props.EnumProperty(
        items=(
            ('ADD', "Add", "Add a new preset"),
            ('REMOVE', "Remove", "Remove the selected preset"),
        )
    )

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        props = context.scene.osc_vse_properties

        if self.action == 'ADD':
            new_preset = prefs.presets.add()
            new_preset.name = "New Preset"
            new_preset.server_ip = props.ip
            new_preset.server_port = props.port
            new_preset.client_ip = props.client_ip
            new_preset.client_port = props.client_port
            prefs.active_preset_index = len(prefs.presets) - 1
            print(f"OSC Preset '{new_preset.name}' added.")

        elif self.action == 'REMOVE':
            if prefs.presets:
                index = prefs.active_preset_index
                prefs.presets.remove(index)
                prefs.active_preset_index = min(max(0, index - 1), len(prefs.presets) - 1)
                print(f"OSC Preset at index {index} removed.")
        
        return {'FINISHED'}


class OSC_PT_VSEPanel(bpy.types.Panel):
    bl_label = "ZOOM surface Control"
    bl_idname = "SEQUENCER_PT_ZOOM"
    bl_space_type = 'SEQUENCE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'ZOOM'
    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__package__].preferences
        props = context.scene.osc_vse_properties

        # --- SECCIÓN DE SERVIDOR ---
        box = layout.box()
        box.label(text="Server Configuration", icon='NETWORK_DRIVE')
        row = box.row()
        row.prop(props, "ip")
        row.prop(props, "port")
        
        if props.is_server_running:
            row = box.row()
            row.label(text="Server Address:")
            row.label(text=f"{props.detected_ip}")
            box.operator("zoom.server_control", text="Stop Server", icon='UNLINKED').action = 'STOP'
        else:
            box.operator("zoom.server_control", text="Start Server", icon='URL').action = 'START'
      
        # --- SECCIÓN DE FEEDBACK ---
        feedback_box = layout.box()
        feedback_box.label(text="Feedback Configuration", icon='SORT_DESC')
        row = feedback_box.row()
        row.prop(props, "client_ip")
        row.prop(props, "client_port")

        # --- SECCIÓN DE PRESETS ---
        preset_box = layout.box()
        preset_box.label(text="Network Presets", icon='PRESET')
        row = preset_box.row()
        row.template_list("UI_UL_osc_presets", "", prefs, "presets", prefs, "active_preset_index")
        
        col = row.column(align=True)
        col.operator("zoom.preset_actions", icon='ADD', text="").action = 'ADD'
        col.operator("zoom.preset_actions", icon='REMOVE', text="").action = 'REMOVE'

        """
        box = layout.box()
        box.label(text="Scrubbing Settings", icon='PREFERENCES')
        box.prop(props, "max_scrub_speed")
        box.prop(props, "min_scrub_speed")
        box.prop(props, "jog_tool_intensity")
        box.prop(props, "jog_relative_speed_divisor")
        transform_box = layout.box()
        transform_box.label(text="Transform Options", icon='OBJECT_DATA')
        transform_box.prop(props, "zoom_snap_value")
        transform_box.prop(props, "position_x_snap_value")
        transform_box.prop(props, "position_y_snap_value")
        transform_box.prop(props, "rotation_snap_value")
        transform_box.prop(props, "origin_x_snap_value")
        transform_box.prop(props, "origin_y_snap_value")
        
        grab_box = layout.box()
        grab_box.label(text="Grab/Translate Settings", icon='DRIVER_TRANSFORM')
        grab_box.prop(props, "grab_user_speed")

        box = layout.box()
        box.prop(props, "show_filters_box",
                 text="Filtros de Selección",
                 icon="FILTER" if props.show_filters_box else "FILTER")
        if props.show_filters_box:
            col = box.column(align=True)
            row = col.row(align=True)
            row.prop(props, "filter_movie", toggle=True)
            row.prop(props, "filter_image", toggle=True)
            row.prop(props, "filter_meta", toggle=True)
            row.prop(props, "filter_audio", toggle=True)
            row = col.row(align=True)
            row.prop(props, "filter_color", toggle=True)
            row.prop(props, "filter_text", toggle=True)
            row.prop(props, "filter_adjustment", toggle=True)
            row.prop(props, "filter_effect_speed", toggle=True)
            row = col.row(align=True)
            row.prop(props, "filter_effect_transform", toggle=True)
            row.prop(props, "filter_transitions", toggle=True)
            row.prop(props, "filter_scene", toggle=True)
            row.prop(props, "filter_clip", toggle=True)
            row = col.row(align=True)
            row.prop(props, "filter_mask", toggle=True)

        """

server_thread_info = {"server": None, "thread": None}

# -------------------- HANDLERS OSC PARA MIRROR --------------------

def handle_auto_mirror(address, args):
    if not args: return
    val = args[0]
    new_state = bool(val) if isinstance(val, (bool, int, float)) else False
    state.control_state["auto_mirror"] = new_state
    print(f"OSC VSE: /auto_mirror -> {new_state}")

def handle_mirror_tolerance(address, args):
    if not args: return
    try:
        val = float(args[0])
    except Exception:
        print("OSC VSE: /mirror_tolerance -> valor inválido")
        return
    state.control_state["mirror_tolerance_sec"] = max(0.0, val)
    print(f"OSC VSE: /mirror_tolerance -> {state.control_state['mirror_tolerance_sec']} sec")

def handle_mirror_range(address, args):
    if not args: return
    try:
        val = int(args[0])
    except Exception:
        print("OSC VSE: /mirror_range -> valor inválido")
        return
    state.control_state["mirror_channel_range"] = max(0, val)
    print(f"OSC VSE: /mirror_range -> {state.control_state['mirror_channel_range']} channels")

# -------------------- FIN HANDLERS MIRROR --------------------

def handle_snap_toggle(address, args):
    if not args: return
    val = args[0]
    new_state = bool(val) if isinstance(val, (bool, int, float)) else False
    state.control_state["snap_active"] = new_state
    print(f"OSC VSE: /snapto -> {new_state}")
    try:
        if hasattr(strips_tools, "_rebuild_snap_targets"):
            strips_tools._rebuild_snap_targets()
    except Exception as e:
        print(f"OSC VSE: error calling strips_tools._rebuild_snap_targets(): {e}")

def handle_snap_target_toggle(address, args):
    if not args: return
    val = args[0]
    new_state = bool(val) if isinstance(val, (bool, int, float)) else False
    part = address.lstrip('/')
    if part.startswith("snap_"):
        key = part[len("snap_"):]
    else:
        key = part
    if "snap_targets" not in state.control_state:
        state.control_state["snap_targets"] = {}
    state.control_state["snap_targets"][key] = new_state
    print(f"OSC VSE: /{part} -> {new_state}")
    try:
        if hasattr(strips_tools, "_rebuild_snap_targets"):
            strips_tools._rebuild_snap_targets()
    except Exception as e:
        print(f"OSC VSE: error calling strips_tools._rebuild_snap_targets(): {e}")

command_handler_map = {
    "/hold_next": transport_extra.handle_transport_hold,
    "/hold_previous": transport_extra.handle_transport_hold,
    "/toggle_play": transport_extra.handle_play_logic,
    "/shift": transport_extra.handle_shift_logic,
    "/Jog": transport_extra.handle_jog_logic,
    "/Jog_value": transport_extra.handle_jog_value,
    "/jog_relative": transport_extra.handle_jog_relative_toggle,
    "/timejump": transport_extra.handle_timeline_jump,
    "/timecode": transport_extra.handle_timecode_feedback_toggle,
    "/esc": transport_extra.handle_escape_logic,
    "/Vstrip": strips_extra.handle_strip_selection,
    "/Nstrip": strips_extra.handle_next_strip,
    "/Pstrip": strips_extra.handle_prev_strip,
    "/plus": strips_extra.handle_selection_plus_minus,
    "/minus": strips_extra.handle_selection_plus_minus,
    "/set_selection": strips_extra.handle_set_selection,
    "/quick_select_next": quicks.handle_quick_select,
    "/quick_select_prev": quicks.handle_quick_select,
    "/quick_delete": quicks.handle_quick_delete,
    "/quick_type_lock": quicks.handle_filter_toggle,
    "/quick_channel_lock": quicks.handle_filter_toggle,
    "/undo": simple_commands.handle_undo,
    "/redo": simple_commands.handle_redo,
    "/copy": simple_commands.handle_copy,
    "/paste": simple_commands.handle_paste,
    "/duplicate": simple_commands.handle_duplicate,
    "/toggle_mute": simple_commands.handle_toggle_mute,
    "/toggle_lock": simple_commands.handle_toggle_lock,
    "/save": simple_commands.handle_save,
    "/save_incremental": simple_commands.handle_save_incremental,
    "/edit_meta": simple_commands.handle_edit_meta,
    "/set_start": simple_commands.handle_set_start,
    "/set_end": simple_commands.handle_set_end,    
    "/frame_clear": strips_tools.handle_frame_clear,
    "/prev_range": strips_tools.handle_set_preview_range,
    "/del_range": strips_tools.handle_delete_preview_range,
    "/Fcur": transport_extra.handle_follow_toggle,
    "/Fcur_tag": strips_extra.handle_fcur_tag,
    "/zoom": tools_extra.handle_tool_activation,
    "/posx": tools_extra.handle_tool_activation,
    "/posy": tools_extra.handle_tool_activation,
    "/rot": tools_extra.handle_tool_activation,
    "/origx": tools_extra.handle_tool_activation,
    "/origy": tools_extra.handle_tool_activation,
    "/alpha": tools_extra.handle_tool_activation,
    "/blend": tools_extra.handle_tool_activation,
    "/cur_strip": strips_extra.handle_cur_strip,
    "/crop_l": tools_extra.handle_tool_activation,
    "/crop_r": tools_extra.handle_tool_activation,
    "/crop_t": tools_extra.handle_tool_activation,
    "/crop_b": tools_extra.handle_tool_activation,
    "/mirror_x": tools_extra.handle_tool_activation,
    "/mirror_y": tools_extra.handle_tool_activation,
    "/reverse": tools_extra.handle_tool_activation,
    "/saturation": tools_extra.handle_tool_activation,
    "/multiply": tools_extra.handle_tool_activation,
    "/volume": audio_internal.handle_tool_activation,
    "/audio_pan": audio_internal.handle_tool_activation,
    "/use_alimit": audio_internal.handle_audio_snap_toggle,
    "/pblend": strips_extra.handle_blend_mode_cycle,
    "/nblend": strips_extra.handle_blend_mode_cycle,
    "/sync_blend": strips_extra.handle_blend_mode_cycle,
    "/use_limit": tools_extra.handle_use_snap_limit_toggle,
    "/key_auto": tools_extra.handle_autokey_toggle,
    "/jump_start": transport_extra.handle_jump_start,
    "/jump_end": transport_extra.handle_jump_end,
    "/frame_next": transport_extra.handle_frame_next,
    "/frame_prev": transport_extra.handle_frame_prev,
    "/key_next": transport_extra.handle_key_next,
    "/key_prev": transport_extra.handle_key_prev,
    "/marker_next": transport_extra.handle_marker_next,
    "/marker_prev": transport_extra.handle_marker_prev,
    "/cursor_lock": transport_extra.handle_cursor_lock,
    "/toggle_audio": transport_extra.handle_toggle_audio,
    "/toggle_audio_scrub": transport_extra.handle_toggle_audio_scrub,
    "/grab": strips_tools.handle_translate_activation,
    "/off_start": tools_extra.handle_tool_activation,
    "/off_end": tools_extra.handle_tool_activation,
    "/select_grouped_on_exit": strips_tools.handle_select_grouped_on_exit_toggle,
    "/knife": strips_tools.handle_knife_activation,
    "/knife_h": strips_tools.handle_knife_activation,
    "/ripple": strips_advance.handle_ripple_activation,
    "/splice": strips_advance.handle_splice_tool,
    "/insert": strips_advance.handle_insert_activation,
    "/add_movie": adds.handle_add_generic,
    "/add_image": adds.handle_add_generic,
    "/add_imseq": adds.handle_add_generic,
    "/add_audio": adds.handle_add_generic,
    "/add_scene": adds.handle_add_generic,
    "/add_text": adds.handle_add_generic,
    "/add_color": adds.handle_add_generic,
    "/add_adjust": adds.handle_add_generic,
    "/add_marker": adds.handle_add_generic,
    "/add_meta": adds.handle_create_meta,
    "/set_group": strips_extra.handle_set_group,
    "/ungroup": strips_extra.handle_ungroup,
    "/select_grouped": strips_extra.handle_select_grouped,
    "/display_groups": strips_extra.handle_display_groups,
    "/group_from_new": groups_logic.handle_group_from_new,
    "/auto_mirror": handle_auto_mirror,
    "/mirror_tolerance": handle_mirror_tolerance,
    "/mirror_range": handle_mirror_range,
    "/snapto": strips_tools.handle_snap_toggle,
    "/snap_startstrips": strips_tools.handle_snap_target_toggle,
    "/snap_endstrips": strips_tools.handle_snap_target_toggle,
    "/snap_audiostrips": strips_tools.handle_snap_target_toggle,
    "/snap_mutestrips": strips_tools.handle_snap_target_toggle,
    "/snap_marker": strips_tools.handle_snap_target_toggle,
    "/snap_keyframe": strips_tools.handle_snap_target_toggle,
    "/snap_playhead": strips_tools.handle_snap_target_toggle,
    "/snap_start": strips_tools.handle_snap_target_toggle,
    "/snap_end": strips_tools.handle_snap_target_toggle,
    "/slip": offsets_tools.handle_slip_activation,
    "/push": offsets_tools.handle_push_activation,
    "/pull": offsets_tools.handle_pull_activation,
    "/sleat": offsets_tools.handle_sleat_activation,
    "/slide": offsets_tools.handle_slide_activation,
    "/select_last_grouped": strips_extra.handle_select_last_grouped,
    "/select_last_trigger": strips_extra.handle_select_last_grouped_trigger,
    "/fade_in_cursor": fades.handle_fade_in_to_cursor,
    "/fade_out_cursor": fades.handle_fade_out_from_cursor,
    "/crossfade_overlap": fades.handle_crossfade_from_overlap,
    "/fade_curve": fades.handle_fade_curve_toggle,
    "/CAM": bl_cam.handle_cam_index,  # index directo
    "/camera/resync_database": lambda addr, args=None: bl_cam.rebuild_database_from_vse(),
    "/camera/autocut_toggle": lambda addr, args=None: state.control_state.__setitem__("auto_cut", bool(args[0] if args else 0)),
    "/camera/container": bl_cam_prop.handle_container_toggle,
    "/camera/cleanup_layer": bl_cam_prop.handle_cleanup,
    "/dolly": bl_cam_prop.handle_camera_tool_activation,
    "/truck": bl_cam_prop.handle_camera_tool_activation,
    "/pedestal": bl_cam_prop.handle_camera_tool_activation,
    "/pan": bl_cam_prop.handle_camera_tool_activation,
    "/tilt": bl_cam_prop.handle_camera_tool_activation,
    "/roll": bl_cam_prop.handle_camera_tool_activation,
    "/focal_length": bl_cam_optics.handle_optics_tool_activation,
    "/shift_x": bl_cam_optics.handle_optics_tool_activation,
    "/shift_y": bl_cam_optics.handle_optics_tool_activation,
    "/use_dof": bl_cam_optics.handle_dof_toggle,
    "/dof_distance": bl_cam_optics.handle_optics_tool_activation,
    "/fstop": bl_cam_optics.handle_optics_tool_activation,
    "/dia_blades": bl_cam_optics.handle_optics_tool_activation,
    "/dia_rot": bl_cam_optics.handle_optics_tool_activation,
    "/dist_ratio": bl_cam_optics.handle_optics_tool_activation,
    "/render": exports.handle_render,
    "/export/play_render": exports.handle_play_render,
    

 }

filter_commands = {
    "/movie": strips_extra.handle_filter_toggle,
    "/image": strips_extra.handle_filter_toggle,
    "/meta": strips_extra.handle_filter_toggle,
    "/color": strips_extra.handle_filter_toggle,
    "/text": strips_extra.handle_filter_toggle,
    "/adjust": strips_extra.handle_filter_toggle,
    "/speed": strips_extra.handle_filter_toggle,
    "/trans": strips_extra.handle_filter_toggle,
    "/scene": strips_extra.handle_filter_toggle,
    "/tranf": strips_extra.handle_filter_toggle,
    "/mask": strips_extra.handle_filter_toggle,
    "/clip": strips_extra.handle_filter_toggle,
    "/audio": strips_extra.handle_filter_toggle,
    "/glow": strips_extra.handle_filter_toggle,
    "/blur": strips_extra.handle_filter_toggle,
}
command_handler_map.update(filter_commands)

def call_logic_on_main_thread(handler_func, address, args):
    try:
        handler_func(address, args)
    except Exception as e:
        print(f"Error calling handler '{handler_func.__name__}': {e}")
    return None

def handle_osc_command(address, *args):

    if address.endswith("_info") and address.startswith("/macro/"):
        if not args or not args[0]: return 
        try:
            num_str = address.split('/')[-1].replace('_info', '')
            num = int(num_str)
            description = macros.get_preset_description(num)
            osc_feedback.send("/macro/info_text", description)
        except (ValueError, IndexError):
            osc_feedback.send("/macro/info_text", "Error")
        return # Terminamos aquí, no continuamos procesando

    # --- LÓGICA PARA EJECUTAR MACROS ---
    if address.startswith("/macro/"):
        try:
            num = int(address.split("/")[-1])
        except Exception:
            print(f"[OSC] Dirección macro inválida: {address}")
            osc_feedback.send("/msg", f"Macro inválida: {address}")
            return
        macros.run_macro(num, context=None, *args[1:])
        return

    # --- manejo especial de multicam ---

    if address.startswith("/CAM/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, bl_cam.handle_cam_index, address, args)
        )
        return
    
    if address == "/multicam_cut":
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, tools_fx.handle_multicam_cut_mode_toggle, address, args)
        )
        return

    if address.startswith("/multicam/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, tools_fx.handle_multicam_command, address, args)
        )
        return
    
    if address.startswith("/channel_lock/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, channels.handle_channel_lock, address, args)
        )
        return

    if address.startswith("/channel_mute/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, channels.handle_channel_mute, address, args)
        )
        return
    
    # --- INICIO: ENRUTAMIENTO PARA MODIFICADORES ---

    if address.startswith("/strip/modifier/inspect/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, modifiers.handle_modifier_inspect, address, args)
        )
        return

    if address.startswith("/add_"):

        type_suffix = address.split('/')[-1].replace('add_', '')
        if type_suffix in modifiers.ADD_MODIFIER_MAP:
            bpy.app.timers.register(
                functools.partial(call_logic_on_main_thread, modifiers.handle_modifier_add, address, args)
            )
            return

    if address.startswith("/curve"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, modifiers.handle_curve_command, address, args)
        )
        return
    
    if address.startswith("/eq/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, modifiers.handle_eq_command, address, args)
        )
        return
    
    if address.startswith("/add_fx/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, adds_fx.handle_add_fx, address, args)
        )
        return
    
    if address.startswith("/strip_fx/"):
        fx_handlers = {
            "/strip_fx/speed": tools_fx.handle_speed_tool_activation,
            "/strip_fx/sp_next": tools_fx.handle_speed_method_cycle,
            "/strip_fx/sp_prev": tools_fx.handle_speed_method_cycle,
            "/strip_fx/sync_sp_method": tools_fx.handle_speed_method_sync,
            "/strip_fx/sp_ajust": tools_fx.handle_recalculate_length,
            "/strip_fx/sp_interpolate": tools_fx.handle_interpolate_toggle,
            "/strip_fx/wipe_type_next": tools_fx.handle_wipe_type_cycle,
            "/strip_fx/wipe_type_prev": tools_fx.handle_wipe_type_cycle,
            "/strip_fx/sync_wipetype": tools_fx.handle_wipe_type_sync,
            "/strip_fx/wipe_type": tools_fx.handle_wipe_type_keyframe,
            "/strip_fx/wipe_direction": tools_fx.handle_wipe_direction_toggle,
            "/strip_fx/wipe_default_fade": tools_fx.handle_wipe_default_fade_toggle,
            "/strip_fx/wipe_blur": tools_fx.handle_wipe_tool_activation,
            "/strip_fx/wipe_angle": tools_fx.handle_wipe_tool_activation,
            "/strip_fx/wipe_fader": tools_fx.handle_wipe_tool_activation,
            "/strip_fx/cross_default_fade": tools_fx.handle_cross_default_fade_toggle,
            "/strip_fx/cross_fader": tools_fx.handle_fx_tool_activation,
            "/strip_fx/blur_x": tools_fx.handle_fx_tool_activation,
            "/strip_fx/blur_y": tools_fx.handle_fx_tool_activation,
            "/strip_fx/glow_only_boost": tools_fx.handle_glow_only_boost_toggle,
            "/strip_fx/glow_threshold": tools_fx.handle_fx_tool_activation,
            "/strip_fx/glow_clamp": tools_fx.handle_fx_tool_activation,
            "/strip_fx/glow_boost": tools_fx.handle_fx_tool_activation,
            "/strip_fx/glow_blur": tools_fx.handle_fx_tool_activation,
            "/strip_fx/glow_quality": tools_fx.handle_fx_tool_activation,
            "/strip_fx/transf_inter": tools_fx.handle_transform_interpolation_cycle,
            "/strip_fx/transf_inter_sync": tools_fx.handle_transform_interpolation_sync,
            "/strip_fx/transf_unit": tools_fx.handle_transform_unit_toggle,
            "/strip_fx/transf_unit_sync": tools_fx.handle_transform_unit_sync,
            "/strip_fx/transf_uniform_scale": tools_fx.handle_fx_tool_activation,
            "/strip_fx/transf_pos_x": tools_fx.handle_fx_tool_activation,
            "/strip_fx/transf_pos_y": tools_fx.handle_fx_tool_activation,
            "/strip_fx/transf_scale_x": tools_fx.handle_fx_tool_activation,
            "/strip_fx/transf_scale_y": tools_fx.handle_fx_tool_activation,
            "/strip_fx/transf_rot": tools_fx.handle_fx_tool_activation,
        }
        handler_func = fx_handlers.get(address)
        if handler_func:
            bpy.app.timers.register(
                functools.partial(call_logic_on_main_thread, handler_func, address, args)
            )
            return

    if address.startswith("/modifier_"):
        op_type = address.split('/')[-1]
        global_ops = ["modifier_toggle_mute", "modifier_delete", "modifier_move_up", "modifier_move_down"]
        if op_type in global_ops:
            bpy.app.timers.register(
                functools.partial(call_logic_on_main_thread, modifiers.handle_modifier_global_op, address, args)
            )
        else:
            bpy.app.timers.register(
                functools.partial(call_logic_on_main_thread, modifiers.handle_modifier_edit, address, args)
            )
        return
    
    
    # --- rutas export----

    if address.startswith("/export/preset/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, exports.handle_apply_preset, address, args)
        )
        return
    if address.startswith("/export/scale/"):
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, exports.handle_set_scale, address, args)
        )
        return

    if state.control_state.get('active_tools', set()):
        for tool in list(state.control_state['active_tools']):
            tool_handlers = state.tool_specific_actions.get(tool, {})
            handler_func = tool_handlers.get(address)
            if handler_func:
                bpy.app.timers.register(
                    functools.partial(call_logic_on_main_thread, handler_func, address, args)
                )
                return

    if address == "/del":
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, strips_extra.handle_delete_from_selection_set, address, args)
        )
        return
    
    if address == "/key":
        def _insert_key_handler(addr, args):
            ok = bl_cam_prop.insert_key_current_tool()
            if not ok:
                if hasattr(tools_extra, "handle_insert_keyframe"):
                    tools_extra.handle_insert_keyframe(addr, args)
        bpy.app.timers.register(functools.partial(call_logic_on_main_thread, _insert_key_handler, address, args))
        return
    
    if address == "/mark/translate":
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, markers.handle_mark_translate_activation, address, args)
        )
        return

    if address == "/mark/delete":
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, markers.handle_mark_delete, address, args)
        )
        return    

    handler_func = command_handler_map.get(address)
    if handler_func:
        bpy.app.timers.register(
            functools.partial(call_logic_on_main_thread, handler_func, address, args)
        )
        return

def run_server(ip, port):
    disp = dispatcher.Dispatcher()
    disp.set_default_handler(lambda address, *args: handle_osc_command(address, *args))
    server = osc_server.ThreadingOSCUDPServer((ip, port), disp)
    print(f"Serving on {server.server_address}")
    server_thread_info["server"] = server
    server.serve_forever()

class OSC_OT_ServerControl(bpy.types.Operator):
    bl_idname = "zoom.server_control"
    bl_label = "Start/Stop OSC Server"
    action: bpy.props.EnumProperty(items=[('START', 'Start', 'Start'), ('STOP', 'Stop', 'Stop')])
    def execute(self, context):
        props = context.scene.osc_vse_properties
        if self.action == 'START' and (server_thread_info["thread"] is None or not server_thread_info["thread"].is_alive()):
            try:

                props.detected_ip = _get_local_ip()

                server_thread = threading.Thread(target=run_server, args=(props.ip, props.port))
                server_thread.daemon = True
                server_thread.start()
                server_thread_info["thread"] = server_thread
                props.is_server_running = True
                start_state_monitor()
                self.report({'INFO'}, f"OSC Server started at {props.detected_ip}:{props.port}")
            except Exception as e:
                self.report({'ERROR'}, f"Could not start server: {e}")
        elif self.action == 'STOP' and server_thread_info["server"]:
            stop_state_monitor()
            server_thread_info["server"].shutdown()
            server_thread_info["server"].server_close()
            if server_thread_info["thread"]:
                server_thread_info["thread"].join(timeout=1)
            server_thread_info.update({"server": None, "thread": None})
            props.is_server_running = False
            
            props.detected_ip = "N/A (server stopped)"

            self.report({'INFO'}, "OSC Server stopped.")
        return {'FINISHED'}
    
   

def cleanup_server():
    if server_thread_info["server"]:
        server_thread_info["server"].shutdown()
        server_thread_info["server"].server_close()
        if server_thread_info["thread"]:
            server_thread_info["thread"].join(timeout=1)
    server_thread_info.update({"server": None, "thread": None})

classes = (
    OSCVSEProperties,
    OSC_PT_VSEPanel,
    UI_UL_osc_presets,
    WM_OT_osc_preset_actions,
    OSC_OT_ServerControl
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    bpy.types.Scene.osc_vse_properties = bpy.props.PointerProperty(type=OSCVSEProperties)
    
    if on_load_reset_server_state not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(on_load_reset_server_state)

    if 'camera' in state.tool_specific_actions:
        del state.tool_specific_actions['camera']



def unregister():
    if on_load_reset_server_state in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(on_load_reset_server_state)
    cleanup_server()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    
    if hasattr(bpy.types.Scene, "osc_vse_properties"):
        del bpy.types.Scene.osc_vse_properties