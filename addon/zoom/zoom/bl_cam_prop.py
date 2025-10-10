# bl_cam_prop.py
import bpy
import math
from mathutils import Vector
from . import state
from . import bl_cam

CNTR_PREFIX = "CNTR_"

# --- INICIO: LÓGICA DEL TIMER DE REFRESCO ---

def _continuous_vse_refresh():
    """
    Timer que se ejecuta para forzar la invalidación del caché del VSE.
    Se detiene solo si no hay herramientas de cámara activas.
    """
    camera_tools = {'dolly', 'truck', 'pedestal', 'pan', 'tilt', 'roll'}
    active_tools = state.control_state.get('active_tools', set())

    if not camera_tools.intersection(active_tools):
        state.control_state['vse_refresh_timer'] = None
        return None  # Detiene el timer

    if bpy.context.scene and bpy.context.scene.sequence_editor:
        for strip in bpy.context.selected_sequences:
            if strip.type == 'SCENE':
                # Forzar invalidación rápida del caché del preview
                strip.mute = True
                strip.mute = False

    return 0.05  # Vuelve a ejecutar en 0.05 segundos

# --- FIN: LÓGICA DEL TIMER DE REFRESCO ---

def set_animation_container_flag(active: bool):
    """
    Nuevo comportamiento:
    - Activa/desactiva globalmente (mute/unmute) todas las constraints creadas
      por el sistema de containers (prefijo CNTR_CONS_).
    - Mantiene la llave en state.control_state['animation_container_active'] para compatibilidad.
    """
    new_state = bool(active)
    # Guardar estado por compatibilidad (otras partes del addon pueden leerlo)
    state.control_state['animation_container_active'] = new_state

    # Recorrer todos los objetos y mutear/desmutear constraints con prefijo CNTR_CONS_
    for obj in bpy.data.objects:
        try:
            # Solo objetos con constraints
            if not getattr(obj, "constraints", None):
                continue
            for con in obj.constraints:
                try:
                    if isinstance(con.name, str) and con.name.startswith("CNTR_CONS_"):
                        # mute = False para activar, True para desactivar
                        con.mute = not new_state
                except Exception:
                    # ignorar constraint que no permita .mute o tenga problemas
                    pass
        except Exception:
            pass

    # Mensaje informativo
    print(f"bl_cam_prop: animation containers {'activated' if new_state else 'deactivated'} (global).")

def _lowest_parent_if_empty(camera):
    p = camera.parent
    if not p:
        return None
    if p.type == 'EMPTY':
        return p
    return False

def activate_container_for_camera_if_needed(camera):
    """
    Crea o devuelve un container (Empty) asociado a 'camera'. Reemplaza el uso
    del Child Of por: Copy Rotation (mix_mode='ADD') + Transformation (map 1:1)
    (si no se puede configurar TRANSFORM, cae a COPY_LOCATION con mix_mode='ADD').

    El empty se crea en origen (0,0,0) con rot 0 y scale 1; los constraints son
    los que suman la transform a la cámara.
    """
    if not camera:
        return None

    target_scene = camera.users_scene[0] if camera.users_scene else None
    if not target_scene:
        print(f"bl_cam_prop: La cámara '{camera.name}' no está en ninguna escena.")
        return None

    low = _lowest_parent_if_empty(camera)
    if low is False:
        print("bl_cam_prop: No se puede crear CNTR porque el padre más bajo no es EMPTY (rig protegido).")
        return None

    # Si ya existe un container para esta cámara en la escena, devolverlo
    for o in target_scene.objects:
        if o.name.startswith(CNTR_PREFIX) and camera.name in o.name:
            return o

    frame = bpy.context.scene.frame_current
    safe_cam_name = camera.name.replace(" ", "_")
    ctnr_name = f"{CNTR_PREFIX}{safe_cam_name}_F{frame}"

    # Creamos el empty **en origen** tal como acordamos.
    empty = bpy.data.objects.new(ctnr_name, None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = 0.2
    empty.location = (0.0, 0.0, 0.0)
    empty.rotation_euler = (0.0, 0.0, 0.0)
    empty.scale = (1.0, 1.0, 1.0)

    try:
        col = bl_cam.get_containers_collection(target_scene, create=True)
        if col and empty.name not in col.objects:
            col.objects.link(empty)
    except Exception:
        if empty.name not in target_scene.collection.objects:
            target_scene.collection.objects.link(empty)

    # ----- Forzar evaluación del depsgraph de la cámara para estabilidad -----
    try:
        deps = bpy.context.evaluated_depsgraph_get()
        _ = camera.evaluated_get(deps)  # forzamos evaluación
    except Exception:
        pass

    try:
        bpy.context.view_layer.update()
    except Exception:
        try:
            bpy.context.evaluated_depsgraph_get()
        except Exception:
            pass

    # ----- Ahora aplicamos constraints en la CÁMARA para sumar la transform del empty -----
    try:
        target_obj_for_constraints = camera

        # 1) Copy Rotation (mix_mode='ADD') --> suma rotaciones del empty a la cámara
        try:
            con_rot = target_obj_for_constraints.constraints.new(type='COPY_ROTATION')
            con_rot.name = f"CNTR_CONS_{ctnr_name}_rot"
            con_rot.target = empty
            try:
                con_rot.mix_mode = 'ADD'
            except Exception:
                pass
            try:
                con_rot.owner_space = 'LOCAL'
                con_rot.target_space = 'WORLD'
            except Exception:
                pass
        except Exception as e:
            print(f"bl_cam_prop: fallo creando COPY_ROTATION constraint en {camera.name}: {e}")

        # 2) Preferimos TRANSFORM constraint para location (remap 1:1 con extrapolate)
        transform_created = False
        try:
            con_tr = target_obj_for_constraints.constraints.new(type='TRANSFORM')
            con_tr.name = f"CNTR_CONS_{ctnr_name}_trf"
            con_tr.target = empty
            try:
                con_tr.owner_space = 'LOCAL'
                con_tr.target_space = 'WORLD'
            except Exception:
                pass
            try:
                con_tr.use_motion_extrapolate = True
            except AttributeError:
                try:
                    con_tr.extrapolate = True
                except Exception:
                    pass

            try:
                if hasattr(con_tr, 'use_map_x'):
                    con_tr.use_map_x = True
                if hasattr(con_tr, 'use_map_y'):
                    con_tr.use_map_y = True
                if hasattr(con_tr, 'use_map_z'):
                    con_tr.use_map_z = True

                if hasattr(con_tr, 'from_min_x'):
                    con_tr.from_min_x = 0.0
                    con_tr.from_max_x = 1.0
                    con_tr.from_min_y = 0.0
                    con_tr.from_max_y = 1.0
                    con_tr.from_min_z = 0.0
                    con_tr.from_max_z = 1.0

                if hasattr(con_tr, 'to_min_x'):
                    con_tr.to_min_x = 0.0
                    con_tr.to_max_x = 1.0
                    con_tr.to_min_y = 0.0
                    con_tr.to_max_y = 1.0
                    con_tr.to_min_z = 0.0
                    con_tr.to_max_z = 1.0

                if hasattr(con_tr, 'map_to'):
                    try:
                        con_tr.map_to = 'LOCATION'
                    except Exception:
                        pass
                else:
                    if hasattr(con_tr, 'map_to_x'):
                        try:
                            con_tr.map_to_x = 'LOCATION'
                            con_tr.map_to_y = 'LOCATION'
                            con_tr.map_to_z = 'LOCATION'
                        except Exception:
                            pass
                try:
                    con_tr.mix_mode = 'ADD'
                except Exception:
                    try:
                        con_tr.use_offset = True
                    except Exception:
                        pass

                transform_created = True
            except Exception:
                transform_created = False

        except Exception as e:
            print(f"bl_cam_prop: fallo creando TRANSFORM constraint en {camera.name}: {e}")
            transform_created = False

        if not transform_created:
            try:
                con_loc = target_obj_for_constraints.constraints.new(type='COPY_LOCATION')
                con_loc.name = f"CNTR_CONS_{ctnr_name}_loc"
                con_loc.target = empty
                try:
                    con_loc.mix_mode = 'ADD'
                except Exception:
                    try:
                        con_loc.use_offset = True
                    except Exception:
                        pass
                try:
                    con_loc.owner_space = 'LOCAL'
                    con_loc.target_space = 'WORLD'
                except Exception:
                    pass
            except Exception as e:
                print(f"bl_cam_prop: fallo creando fallback COPY_LOCATION constraint en {camera.name}: {e}")

        try:
            deps = bpy.context.evaluated_depsgraph_get()
            _ = camera.evaluated_get(deps)
            bpy.context.view_layer.update()
        except Exception:
            pass

    except Exception as e:
        print("bl_cam_prop: fallo aplicando constraints aditivos:", e)
        try:
            bpy.data.objects.remove(empty, do_unlink=True)
        except Exception:
            pass
        return None

    state.control_state.setdefault('active_camera_container', empty.name)
    state.control_state['active_camera_container_camera'] = camera.name

    return empty

# ----------------------------
# Helpers para keyframes / auto-record (compartidos)
# ----------------------------
def _insert_keyframes_if_auto_or_forced(container, forced=False):
    """
    Inserta keyframes sobre location/rotation_euler/scale si
    state.control_state['auto_record'] está activo o si forced=True.
    """
    if not container:
        return

    # <-- INICIO: MODIFICACIÓN -->
    # La decisión de insertar un keyframe ahora solo depende de 'forced'
    # o del estado global de 'auto_record'.
    if forced or state.control_state.get('auto_record', False):
    # <-- FIN: MODIFICACIÓN -->

        frame_cur = bpy.context.scene.frame_current
        try:
            active_tools = state.control_state.get('active_tools', set())
            if {'dolly', 'truck', 'pedestal'}.intersection(active_tools):
                container.keyframe_insert(data_path="location", frame=frame_cur)
            if {'pan', 'tilt', 'roll'}.intersection(active_tools):
                container.keyframe_insert(data_path="rotation_euler", frame=frame_cur)
        except Exception:
            pass

# ----------------------------
# Implementación de herramientas de cámara (dolly/truck/pedestal)
# ----------------------------
def apply_dolly(delta):
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    any_ok = False
    for cam in cams:
        ctnr = activate_container_for_camera_if_needed(cam)
        if not ctnr: continue
        try:
            v_local = Vector((0.0, 0.0, delta))
            rot_actual = ctnr.rotation_euler.to_matrix().to_quaternion()
            ctnr.location += rot_actual @ v_local
            _insert_keyframes_if_auto_or_forced(ctnr) # <-- MODIFICADO
            any_ok = True
        except Exception as e:
            print(f"bl_cam_prop.apply_dolly error: {e}")
    return any_ok

def apply_truck(delta):
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    any_ok = False
    for cam in cams:
        ctnr = activate_container_for_camera_if_needed(cam)
        if not ctnr: continue
        try:
            v_local = Vector((delta, 0.0, 0.0))
            rot_actual = ctnr.rotation_euler.to_matrix().to_quaternion()
            ctnr.location += rot_actual @ v_local
            _insert_keyframes_if_auto_or_forced(ctnr) # <-- MODIFICADO
            any_ok = True
        except Exception as e:
            print(f"bl_cam_prop.apply_truck error: {e}")
    return any_ok

def apply_pedestal(delta):
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    any_ok = False
    for cam in cams:
        ctnr = activate_container_for_camera_if_needed(cam)
        if not ctnr: continue
        try:
            v_local = Vector((0.0, delta, 0.0))
            rot_actual = ctnr.rotation_euler.to_matrix().to_quaternion()
            ctnr.location += rot_actual @ v_local
            _insert_keyframes_if_auto_or_forced(ctnr) # <-- MODIFICADO
            any_ok = True
        except Exception as e:
            print(f"bl_cam_prop.apply_pedestal error: {e}")
    return any_ok

# ----------------------------
# Implementación de herramientas de ROTACIÓN (pan/tilt/roll)
# ----------------------------
def apply_tilt(delta_deg):
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    any_ok = False
    for cam in cams:
        ctnr = activate_container_for_camera_if_needed(cam)
        if not ctnr: continue
        try:
            ctnr.rotation_euler.x += math.radians(delta_deg)
            _insert_keyframes_if_auto_or_forced(ctnr) # <-- MODIFICADO
            any_ok = True
        except Exception as e: print("bl_cam_prop.apply_tilt error:", e)
    return any_ok

def apply_pan(delta_deg):
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    any_ok = False
    for cam in cams:
        ctnr = activate_container_for_camera_if_needed(cam)
        if not ctnr: continue
        try:
            ctnr.rotation_euler.y += math.radians(delta_deg)
            _insert_keyframes_if_auto_or_forced(ctnr) # <-- MODIFICADO
            any_ok = True
        except Exception as e: print("bl_cam_prop.apply_pan error:", e)
    return any_ok

def apply_roll(delta_deg):
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    any_ok = False
    for cam in cams:
        ctnr = activate_container_for_camera_if_needed(cam)
        if not ctnr: continue
        try:
            ctnr.rotation_euler.z += math.radians(delta_deg)
            _insert_keyframes_if_auto_or_forced(ctnr) # <-- MODIFICADO
            any_ok = True
        except Exception as e: print("bl_cam_prop.apply_roll error:", e)
    return any_ok

def cleanup_all_containers():
    # ... (sin cambios)
    removed = 0
    to_remove = [o for o in bpy.data.objects if o.name.startswith(CNTR_PREFIX)]
    for o in to_remove:
        try:
            bpy.data.objects.remove(o, do_unlink=True)
            removed += 1
        except Exception:
            pass
    return removed

def insert_key_current_tool():
    # ... (sin cambios)
    tools = state.control_state.get('active_tools', set())
    if not tools: return False
    cams = bl_cam.get_cameras_for_selected_strips()
    if not cams: return False
    frame_cur = bpy.context.scene.frame_current
    any_ok = False
    for cam in cams:
        ctnr = next((o for o in bpy.data.objects if o.name.startswith(CNTR_PREFIX) and cam.name in o.name), None)
        if not ctnr: continue
        try:
            if {'dolly', 'truck', 'pedestal'}.intersection(tools):
                ctnr.keyframe_insert(data_path="location", frame=frame_cur)
                any_ok = True
            if {'pan', 'tilt', 'roll'}.intersection(tools):
                ctnr.keyframe_insert(data_path="rotation_euler", frame=frame_cur)
                any_ok = True
        except Exception as e:
            print(f"bl_cam_prop: fallo al insertar keyframe en {ctnr.name}: {e}")
    return any_ok

def handle_container_toggle(address, args):
    # ... (sin cambios)
    if not args: return
    val = args[0]
    new_state = bool(val) if isinstance(val, (bool, int, float)) else False
    set_animation_container_flag(new_state)
    print(f"bl_cam_prop: /camera/container -> {new_state}")

def handle_cleanup(address, args):
    # ... (sin cambios)
    removed = cleanup_all_containers()
    print(f"bl_cam_prop: Cleanup -> {removed} containers eliminados")

def handle_camera_tool_activation(address, args):
    # ... (sin cambios)
    """
    Manejador dedicado para activar/desactivar herramientas de cámara
    y controlar el timer de refresco del VSE.
    """
    if not args: return
    try:
        is_pressed = bool(args[0])
    except (ValueError, TypeError):
        return
    tool_name = address.strip('/')
    if is_pressed:
        if tool_name not in state.control_state.setdefault('active_tools', set()):
            state.control_state['active_tools'].add(tool_name)
            if state.control_state.get('vse_refresh_timer') is None:
                timer = bpy.app.timers.register(_continuous_vse_refresh, first_interval=0.05)
                state.control_state['vse_refresh_timer'] = timer
    else:
        state.control_state['active_tools'].discard(tool_name)
        # El timer se detendrá solo en su próximo ciclo.

def register_actions():
    # ... (sin cambios)
    """Registra las acciones de jog y plus/minus para las herramientas de cámara."""

    JOG_SENSITIVITY_CAM_LOC = 0.05
    PLUS_MINUS_SENSITIVITY_CAM_LOC = 0.01
    JOG_SENSITIVITY_CAM_ROT = 2.0  # Grados por tick de jog
    PLUS_MINUS_SENSITIVITY_CAM_ROT = 0.5 # Grados por pulsación

    # Herramientas de Localización
    state.jog_actions['dolly'] = lambda val: apply_dolly(val * JOG_SENSITIVITY_CAM_LOC)
    state.jog_actions['truck'] = lambda val: apply_truck(val * JOG_SENSITIVITY_CAM_LOC)
    state.jog_actions['pedestal'] = lambda val: apply_pedestal(val * JOG_SENSITIVITY_CAM_LOC)
    state.plus_minus_actions['dolly'] = lambda d: apply_dolly(d * PLUS_MINUS_SENSITIVITY_CAM_LOC)
    state.plus_minus_actions['truck'] = lambda d: apply_truck(d * PLUS_MINUS_SENSITIVITY_CAM_LOC)
    state.plus_minus_actions['pedestal'] = lambda d: apply_pedestal(d * PLUS_MINUS_SENSITIVITY_CAM_LOC)

    # Herramientas de Rotación
    state.jog_actions['tilt'] = lambda val: apply_tilt(val * JOG_SENSITIVITY_CAM_ROT)
    state.jog_actions['pan'] = lambda val: apply_pan(val * JOG_SENSITIVITY_CAM_ROT)
    state.jog_actions['roll'] = lambda val: apply_roll(val * JOG_SENSITIVITY_CAM_ROT)
    state.plus_minus_actions['tilt'] = lambda d: apply_tilt(d * PLUS_MINUS_SENSITIVITY_CAM_ROT)
    state.plus_minus_actions['pan'] = lambda d: apply_pan(d * PLUS_MINUS_SENSITIVITY_CAM_ROT)
    state.plus_minus_actions['roll'] = lambda d: apply_roll(d * PLUS_MINUS_SENSITIVITY_CAM_ROT)

    # Keyframing
    state.tool_specific_actions['dolly'] = {'/key': lambda a, r: insert_key_current_tool()}
    state.tool_specific_actions['truck'] = {'/key': lambda a, r: insert_key_current_tool()}
    state.tool_specific_actions['pedestal'] = {'/key': lambda a, r: insert_key_current_tool()}
    state.tool_specific_actions['tilt'] = {'/key': lambda a, r: insert_key_current_tool()}
    state.tool_specific_actions['pan'] = {'/key': lambda a, r: insert_key_current_tool()}
    state.tool_specific_actions['roll'] = {'/key': lambda a, r: insert_key_current_tool()}