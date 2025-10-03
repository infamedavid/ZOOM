# state.py

control_state = {
    # --- ESTADOS MANTENIDOS ---
    "is_playing": False,
    "play_direction": "fwd",
    "shift_active": False, #<------ es la tecla Fn en la superfice de control

    # --- ACTIVE TOOL ---
    "active_tools": set(),  

    # --- JOG Y TIMELINE ---
    "jog_active": False,
    "jog_value": 0.0,
    "jog_timer": None,
    "last_nav_time": 0.0,
    "jog_relative_mode": False,
    "jog_frame_accumulator": 0.0,
    "offset_frame_accumulator": 0.0,
    "timecode_feedback_active": True,
    "timecode_last_send_time": 0.0,
    "strip_time_timer": None,

    # --- SCENE MULTICAM---
    "auto_cut": False,  # modo edit (True) vs preview (False)
    "camera_map": {},   # cache opcional scene.name -> camera list
    # --- MULTICAM ---
    "multicam_cut_mode": False,
    "multicam_context": {},


    # --- Animation Container (CTNR) ---
    "animation_container_active": False,  # esto ahora es para habilitar/ deshabilitar los constraints del container
    "active_camera_container": None,
    "active_camera_container_camera": None,

    # --- BANDERA PARA EL LÍMITE/SNAP OPCIONAL ---
    "use_snap_limit": False,

    # --- ESTADOS PARA EL SISTEMA "COLOR TAG" ---
    "strip_nav_active": False,
    "selection_set": set(),
    "last_vstrip_press_time": 0.0,
    "strip_nav_follow_active": False,
    "preview_strip_name": None,
    
    # --- ESTADOS PARA EL SISTEMA DE GRUPOS ---
    "select_grouped_on_exit": True,
    "tool_temp_linked_selection": set(),
    "display_groups_active": False,

    # ---  ESTADOS PARA EL ZOOM POR PASOS ---
    "zoom_level": None,
    "zoom_length": None,
    "zoom_start_frame": None,

    # --- ESTADOS PARA LA HERRAMIENTA RIPPLE ---
    "ripple_initial_gap": 0,
    "ripple_sign_state": 0,

    # --- SISTEMA DE SNAP ---
    "snap_active": False,
    "snap_targets": {
        "startstrips": True,
        "endstrips": True,
        "audiostrips": True,
        "mutestrips": True,
        "marker": False,
        "keyframe": False,
        "playhead": False,
        "start": False,
        "end": False,
    },

    # --- MODIFICADORES DE STRIP ---
    "active_modifier_strip_name": None,  # Guarda el nombre del strip activo para modificadores.
    "active_modifier_stack_index": None, # Guarda el índice en el stack del modificador activo.

    "active_curve_channel": None,   # Canal activo: 'C', 'R', 'G', 'B'
    "active_curve_node_index": None, # Índice real del nodo en la curva de Blender
    "active_curve_node_slot": None,  # Slot del botón presionado en la UI (1-5)

    # --- MIRROR AUTOMÁTICO ---
    "auto_mirror": True,           # activar/desactivar mirror automático
    "mirror_tolerance_sec": 0.0,   # tolerancia en segundos
    "mirror_channel_range": 2,     # rango de canales (int)
    "last_group_id": None,         # id del último grupo creado

    # --- Auto selección del último grupo creado (por /select_last_grouped) ---
    "auto_select_last_grouped": True,
    
    # --- Registro de strips conocidos ---
    "known_strip_names": set(),

    # --- ESTADO PARA AUTO-RECORD ---
    "auto_record": False,

    # --- ESTADO PARA MODULO FADES ---
    "fade_curve_type": "LINEAR",

    # -- FEEDBACK Y SYNC --
    "last_sent_tool": "none",
    "active_tool_custom_name": None,
    "state_monitor_timer": None,
    "export_feedback_timer": None,
    
}

# Diccionarios auxiliares para acciones dinámicas
plus_minus_actions = {}
jog_actions = {}
tool_specific_actions = {}
