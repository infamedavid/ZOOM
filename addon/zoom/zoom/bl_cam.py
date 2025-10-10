# bl_cam.py
"""
Gestión Multicam para OSC VSE.
- Persistencia en bpy.data.texts -> "osc_vse_cam_data.json"
- UUIDs por strip -> strip["osc_vse_uuid"]
- Handler /CAM/N (preview vs auto_cut edit)
- Resync via undo_post / save_post
- CTNR_Empty controllers en colección oculta "Editor Containers"
- Modo interactivo: al cortar, el strip derecho se sube a canal libre y se queda
  en modo "camera" esperando jog para overlap/gap. Al soltar, se finaliza
  aplicando crossfade con keyframes si overlap >= 2 (igual que SPLICE).
"""

import bpy
import json
import uuid
import math
from bpy.app.handlers import persistent
from . import state

TEXTBLOCK_NAME = "osc_vse_cam_data.json"
CONTAINERS_COLLECTION = "Editor Containers"
UUID_PROP = "osc_vse_uuid"


# ----------------------------
# Text-block (JSON) utilities
# ----------------------------
def ensure_textblock():
    tb = bpy.data.texts.get(TEXTBLOCK_NAME)
    if not tb:
        tb = bpy.data.texts.new(TEXTBLOCK_NAME)
        tb.from_string(json.dumps({}, indent=2))
    return tb

def load_camera_data():
    tb = ensure_textblock()
    try:
        txt = tb.as_string()
        if not txt.strip():
            return {}
        data = json.loads(txt)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print("bl_cam.load_camera_data error:", e)
        return {}

def save_camera_data(data):
    tb = ensure_textblock()
    try:
        tb.clear()
        tb.write(json.dumps(data, indent=2))
    except Exception as e:
        print("bl_cam.save_camera_data error:", e)


# ----------------------------
# UUID helpers
# ----------------------------
def ensure_strip_uuid(strip):
    if not strip:
        return None
    if UUID_PROP in strip:
        return strip[UUID_PROP]
    u = str(uuid.uuid4())
    try:
        strip[UUID_PROP] = u
    except Exception as e:
        print("bl_cam.ensure_strip_uuid fail:", getattr(strip, "name", None), e)
        return None
    return u

def get_strip_uuid(strip):
    return strip.get(UUID_PROP, None)


def get_cameras_for_selected_strips():
    """
    Devuelve una lista de objetos de cámara únicos basados en los strips de Escena seleccionados en el VSE.
    """
    cameras = set()
    sequencer = bpy.context.scene.sequence_editor
    if not sequencer:
        return []

    selected_strips = bpy.context.selected_sequences
    if not selected_strips:
        # Si no hay nada seleccionado, intenta usar el strip activo
        if sequencer.active_strip:
            selected_strips = [sequencer.active_strip]
        else:
            return []

    for strip in selected_strips:
        # Se asegura de que el strip sea de tipo 'SCENE' y tenga una cámara asignada
        if strip.type == 'SCENE' and strip.scene and strip.scene.camera:
            cameras.add(strip.scene.camera)

    return list(cameras)


# ----------------------------
# Camera map for a given scene
# ----------------------------
def build_camera_map_for_scene(scene):
    cams = [o for o in scene.objects if o.type == 'CAMERA']
    if not cams:
        return []
    default_like, others = [], []
    for c in cams:
        if c.name.startswith("Camera"):
            default_like.append(c)
        else:
            others.append(c)
    def cam_sort_key(o):
        parts = o.name.split('.')
        if len(parts) > 1 and parts[-1].isdigit():
            return (0, parts[0], int(parts[-1]))
        return (0, o.name, 0)
    default_like_sorted = sorted(default_like, key=cam_sort_key)
    others_sorted = sorted(others, key=lambda o: o.name.lower())
    return default_like_sorted + others_sorted


# ----------------------------
# CTNR_Empty management (se mantiene, posible uso futuro)
# ----------------------------
def get_containers_collection(scene, create=True):
    if not scene: return None
    col = bpy.data.collections.get(CONTAINERS_COLLECTION)
    if not col and create:
        col = bpy.data.collections.new(CONTAINERS_COLLECTION)
        # Lo linkeamos a la escena correcta, no a bpy.context.scene
        scene.collection.children.link(col)
    return col

def get_or_create_controller_for_camera(camera):
    if not camera:
        return None
    controllers = state.control_state.get("camera_controllers", {})
    if controllers is None:
        controllers = {}
        state.control_state["camera_controllers"] = controllers

    ctr_name = f"CTNR_{camera.name}"
    existing = controllers.get(camera.name)
    if existing:
        obj = bpy.data.objects.get(existing)
        if obj:
            return obj
        else:
            controllers.pop(camera.name, None)

    empty = bpy.data.objects.new(ctr_name, None)
    empty.empty_display_size = 0.1
    empty.empty_display_type = 'PLAIN_AXES'
    empty.parent = camera

    target_scene = camera.users_scene[0] if camera.users_scene else bpy.context.scene
    col = get_containers_collection(target_scene, True)
    if col and empty.name not in col.objects:
        try:
            col.objects.link(empty)
        except Exception:
            if empty.name not in target_scene.collection.objects:
                target_scene.collection.objects.link(empty)

    controllers[camera.name] = empty.name
    state.control_state["camera_controllers"] = controllers
    return empty


# ----------------------------
# Frame mapping VSE -> Scene
# ----------------------------
def map_vse_frame_to_scene_frame(strip, vse_frame):
    if not strip or strip.type != 'SCENE' or not strip.scene:
        return None
    scene_start = getattr(strip.scene, "frame_start", 1)
    return int(round(scene_start + (vse_frame - strip.frame_start)))


# ----------------------------
# Utilities copied / adapted from strips_advance (visible ranges & crossfade helpers)
# ----------------------------
def _get_visible_range(strip):
    """Devuelve el rango visible (start, end) de un strip (enteros)."""
    if hasattr(strip, "frame_final_start") and hasattr(strip, "frame_final_end"):
        return int(strip.frame_final_start), int(strip.frame_final_end)
    else:
        start = int(strip.frame_start)
        duration = int(getattr(strip, "frame_duration", getattr(strip, "frame_final_duration", 0)))
        return start, int(start + duration)

def _clear_crossfade_keyframes(strips):
    """Elimina keyframes de blend_alpha y volume y restaura valores por defecto."""
    if not strips:
        return
    for strip in strips:
        if not strip:
            continue
        try:
            if hasattr(strip, 'blend_alpha'):
                strip.blend_alpha = 1.0
            if hasattr(strip, 'volume'):
                strip.volume = 1.0
            if strip.animation_data and strip.animation_data.action:
                action = strip.animation_data.action
                # buscar y remover fcurves
                to_remove = []
                if hasattr(strip, 'blend_alpha'):
                    fc = action.fcurves.find('blend_alpha')
                    if fc: to_remove.append(fc)
                if hasattr(strip, 'volume'):
                    fc = action.fcurves.find('volume')
                    if fc: to_remove.append(fc)
                for fc in reversed(to_remove):
                    action.fcurves.remove(fc)
        except Exception:
            # No todos los strips tienen animation_data o props; ignoramos fallos
            pass

def _apply_crossfade_keyframes(preceding, rippled, overlap_duration):
    """
    Aplica keyframes de blend_alpha (video) y volume (audio) entre preceding (left)
    y rippled (right) usando interpolación LINEAR. overlap_duration en frames (>0).
    """
    if not preceding or not rippled or overlap_duration <= 0:
        return

    start_frame = _get_visible_range(rippled)[0]
    end_frame = start_frame + overlap_duration

    # Si no hay rango real para transición, limpiar y salir
    if start_frame >= end_frame:
        _clear_crossfade_keyframes([preceding, rippled])
        return

    def apply_safe_keyframes(strip, prop_name, start_val, end_val):
        # limpiar keyframes previos en rango
        try:
            if strip.animation_data and strip.animation_data.action:
                fcurve = strip.animation_data.action.fcurves.find(prop_name)
                if fcurve:
                    points_to_remove = [p for p in fcurve.keyframe_points if start_frame <= p.co.x <= end_frame]
                    for p in reversed(points_to_remove):
                        fcurve.keyframe_points.remove(p)
        except Exception:
            pass

        # insertar keyframes
        try:
            setattr(strip, prop_name, start_val)
            strip.keyframe_insert(data_path=prop_name, frame=start_frame)
            setattr(strip, prop_name, end_val)
            strip.keyframe_insert(data_path=prop_name, frame=end_frame)

            # forzar interpolación LINEAR
            try:
                if strip.animation_data and strip.animation_data.action:
                    fcurve = strip.animation_data.action.fcurves.find(prop_name)
                    if fcurve:
                        # asegurar que los puntos que acabamos de insertar sean lineales
                        for kp in fcurve.keyframe_points:
                            if math.isclose(kp.co.x, start_frame) or math.isclose(kp.co.x, end_frame):
                                kp.interpolation = 'LINEAR'
                        fcurve.update()
            except Exception:
                pass

        except Exception as e:
            print(f"bl_cam: apply_safe_keyframes error on '{getattr(strip,'name',None)}' {prop_name}: {e}")

    # aplicar en video: blend_alpha
    if hasattr(preceding, 'blend_alpha') and hasattr(rippled, 'blend_alpha'):
        apply_safe_keyframes(preceding, 'blend_alpha', 1.0, 0.0)
        apply_safe_keyframes(rippled, 'blend_alpha', 0.0, 1.0)

    # aplicar en audio: volume (si aplica)
    if hasattr(preceding, 'volume') and hasattr(rippled, 'volume'):
        apply_safe_keyframes(preceding, 'volume', 1.0, 0.0)
        apply_safe_keyframes(rippled, 'volume', 0.0, 1.0)


# ----------------------------
# Channel finding helper (busca canal libre hacia arriba)
# ----------------------------
def _find_empty_adjacent_channel(strip, scene, look_ahead=20):
    """
    Devuelve el primer canal >= strip.channel + 1 que NO tenga ningún strip
    que se solape en el rango visible de `strip`. look_ahead limita búsqueda.
    """
    try:
        seqs = scene.sequence_editor.sequences_all
    except Exception:
        return strip.channel + 1

    vis_start, vis_end = _get_visible_range(strip)
    target_channel = strip.channel + 1
    max_checked = (max((s.channel for s in seqs), default=target_channel) + look_ahead)
    for ch in range(target_channel, max_checked + 1):
        occupied = False
        for s in seqs:
            if s.channel != ch:
                continue
            s_start, s_end = _get_visible_range(s)
            # si existe superposición (intervalos abiertos en extremos)
            if max(s_start, vis_start) < min(s_end, vis_end):
                occupied = True
                break
        if not occupied:
            return ch
    # fallback: return next channel
    return max_checked + 1


# ----------------------------
# Split / bind algorithm (MODIFICADO)
# ----------------------------
def perform_bind_and_split(active_strip, target_camera_obj, split_vse_frame, auto_cut=False):
    """
    Realiza el binding (marker + scene.camera) y, si auto_cut:
      - split del strip SCENE
      - identifica right_strip (la parte nueva)
      - sube right_strip a un canal libre (inmediato)
      - crea contexto interactivo en state.control_state['multicam_context']
    """
    if not active_strip or active_strip.type != 'SCENE' or not active_strip.scene:
        return None

    source_scene = active_strip.scene
    scene_frame = map_vse_frame_to_scene_frame(active_strip, split_vse_frame)
    if scene_frame is None:
        return None

    # Si se solicita PREVIEW, limpiamos cualquier contexto multicam residual
    # y nos aseguramos de que la herramienta 'camera' no quede activa.
    if not auto_cut:
        if 'multicam_context' in state.control_state:
            try:
                del state.control_state['multicam_context']
            except Exception:
                state.control_state.pop('multicam_context', None)
        try:
            state.control_state.setdefault('active_tools', set()).discard('camera')
        except Exception:
            pass

        # --- PREVIEW MODE ---
        # Solo cambiar la cámara activa para preview, sin crear marker, sin bind a DB, sin cortes.
        source_scene.camera = target_camera_obj

        # Forzar refresco del VSE para que el preview actualice (truco: mute/unmute de SCENE strips)
        try:
            if bpy.context.scene and bpy.context.scene.sequence_editor:
                for strip in bpy.context.selected_sequences:
                    if strip.type == 'SCENE':
                        try:
                            strip.mute = True
                            strip.mute = False
                        except Exception:
                            pass
            try:
                bpy.ops.sequencer.refresh_all()
            except Exception:
                pass
        except Exception:
            pass

        return {"left_uuid": None, "right_uuid": None, "right_strip_name": None}

    # --- AUTO CUT MODE ---
    # create marker and assign camera
    for m in [m for m in source_scene.timeline_markers if m.frame == scene_frame]:
        source_scene.timeline_markers.remove(m)

    marker = source_scene.timeline_markers.new(name=f"Cam_{target_camera_obj.name}", frame=scene_frame)
    marker.camera = target_camera_obj
    source_scene.camera = target_camera_obj

    data = load_camera_data()
    ensure_strip_uuid(active_strip)
    left_uuid = get_strip_uuid(active_strip)

    # --- INICIO DE LA LÓGICA ROBUSTA DE CORTE Y SELECCIÓN ---
    scene_vse = bpy.context.scene
    sequencer = scene_vse.sequence_editor

    # 1. Snapshot de los strips existentes.
    names_before_cut = {s.name for s in sequencer.sequences_all}

    right_strip = None
    try:
        # Asegurar que solo el strip activo está seleccionado para el corte
        for s in sequencer.sequences_all:
            s.select = (s.name == active_strip.name)

        scene_vse.frame_current = split_vse_frame
        bpy.ops.ed.undo_push(message="OSC Camera AutoCut")
        bpy.ops.sequencer.split(frame=split_vse_frame)
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        # 2. Identificar el nuevo strip comparando el snapshot.
        all_strips_after_cut = sequencer.sequences_all
        new_strip_names = {s.name for s in all_strips_after_cut} - names_before_cut

        if not new_strip_names:
            raise Exception("El corte no produjo un nuevo strip.")

        right_strip_name = new_strip_names.pop()
        right_strip = sequencer.sequences_all.get(right_strip_name)

        if not right_strip:
            raise Exception(f"No se pudo encontrar el nuevo strip '{right_strip_name}'.")

    except Exception as e:
        print(f"bl_cam.perform_bind_and_split error en el corte: {e}")
        return None

    # A partir de aquí, 'right_strip' es una referencia 100% fiable.
    ensure_strip_uuid(active_strip)
    left_uuid = get_strip_uuid(active_strip)

    if right_strip:
        ensure_strip_uuid(right_strip)
        right_uuid = get_strip_uuid(right_strip)

        # subimos right_strip a canal libre inmediatamente (para indicar cambio de cámara)
        orig_channel = right_strip.channel
        new_channel = _find_empty_adjacent_channel(active_strip, scene_vse, look_ahead=20)
        try:
            right_strip.channel = new_channel
        except Exception:
            # fallback: sumar 1
            right_strip.channel = orig_channel + 1

        # Guardar mapping para right strip y DB
        data[right_uuid] = target_camera_obj.name
        save_camera_data(data)

        # Crear contexto interactivo (igual que splice) para que jog/nudge lo manejen
        ctx = {
            'left_name': active_strip.name,
            'right_name': right_strip.name,
            'original_channel': orig_channel,
            'interactive_started': False,
            'accumulated_delta': 0.0,
        }
        state.control_state['multicam_context'] = ctx
        state.control_state.setdefault('active_tools', set()).add('camera')

        # Determinar overlap inmediato (puede ser 0)
        left_vis = _get_visible_range(active_strip)
        right_vis = _get_visible_range(right_strip)
        initial_overlap = max(0, left_vis[1] - right_vis[0])
        if initial_overlap >= 2:
            _apply_crossfade_keyframes(active_strip, right_strip, initial_overlap)

        # 3. Gestión explícita de la selección para estabilizar el contexto.
        bpy.ops.sequencer.select_all(action='DESELECT')
        right_strip.select = True
        sequencer.active_strip = right_strip

        try:
            bpy.ops.sequencer.refresh_all()
        except Exception:
            pass

        return {"left_uuid": left_uuid, "right_uuid": right_uuid, "right_strip_name": right_strip.name}
    else:
        # no right strip encontrado (raro)
        if left_uuid:
            data[left_uuid] = target_camera_obj.name
            save_camera_data(data)
        return {"left_uuid": left_uuid, "right_uuid": None, "right_strip_name": None}


# ----------------------------
# Interactivos: movimiento por jog / nudge y finalización
# ----------------------------
def _perform_camera_from_jog(jog_value):
    """
    Mueve el right_strip en contexto 'multicam_context' proporcionalmente al jog_value.
    Este handler se conecta a state.jog_actions['camera'].
    """
    ctx = state.control_state.get('multicam_context')
    sequencer = bpy.context.scene.sequence_editor
    if not ctx or not sequencer:
        return

    right_name = ctx.get('right_name')
    right_strip = sequencer.sequences_all.get(right_name)
    left_strip = sequencer.sequences_all.get(ctx.get('left_name'))
    if not right_strip or not left_strip:
        return

    # sensibilidad: usar la propiedad del addon si existe
    try:
        intensity = bpy.context.scene.osc_vse_properties.jog_tool_intensity
    except Exception:
        intensity = 1.0

    # Mapear jog_value a delta frames (similar a splice)
    delta = int(round(jog_value * intensity * 5.0))  # factor 5 = sensible pero progresivo
    if delta == 0:
        return

    # marcar interactive_started y mover a canal seguro (ya subido en perform_bind_and_split)
    if not ctx.get('interactive_started'):
        ctx['interactive_started'] = True

    # Aplicar movimiento (sumamos delta)
    right_strip.frame_start += delta
    ctx['accumulated_delta'] += delta

    # Clamp mínimo para no sacar del timeline (simple)
    if right_strip.frame_start < 0:
        right_strip.frame_start = 0

    # Opcional: seguimiento del cabezal similar a splice
    if state.control_state.get('strip_nav_follow_active', False):
        target_frame = _get_visible_range(right_strip)[0] - 1
        bpy.context.scene.frame_current = max(bpy.context.scene.frame_start, target_frame)


def _perform_camera_from_nudge(direction):
    """Nudge por +1 / -1 frames (mapear a plus/minus)."""
    # direction expected +1 or -1
    ctx = state.control_state.get('multicam_context')
    sequencer = bpy.context.scene.sequence_editor
    if not ctx or not sequencer:
        return
    right_name = ctx.get('right_name')
    right_strip = sequencer.sequences_all.get(right_name)
    if not right_strip:
        return
    delta = int(direction)
    right_strip.frame_start += delta
    ctx['accumulated_delta'] += delta
    if right_strip.frame_start < 0:
        right_strip.frame_start = 0
    if state.control_state.get('strip_nav_follow_active', False):
        target_frame = _get_visible_range(right_strip)[0] - 1
        bpy.context.scene.frame_current = max(bpy.context.scene.frame_start, target_frame)


def _finalize_camera_cut():
    """
    Finaliza la operación multicam del contexto: aplica crossfade si overlap >= 2,
    o restaura canal original si no hay overlap.
    Borra contexto y desactiva la herramienta 'camera'.
    """
    ctx = state.control_state.get('multicam_context')
    sequencer = bpy.context.scene.sequence_editor
    if not ctx or not sequencer:
        # limpiar por si acaso
        if 'multicam_context' in state.control_state:
            del state.control_state['multicam_context']
        state.control_state.setdefault('active_tools', set()).discard('camera')
        return

    left = sequencer.sequences_all.get(ctx.get('left_name'))
    right = sequencer.sequences_all.get(ctx.get('right_name'))
    orig_channel = ctx.get('original_channel', None)

    if not left or not right:
        # limpieza segura
        if 'multicam_context' in state.control_state:
            del state.control_state['multicam_context']
        state.control_state.setdefault('active_tools', set()).discard('camera')
        return

    left_vis = _get_visible_range(left)
    right_vis = _get_visible_range(right)
    overlap = max(0, left_vis[1] - right_vis[0])

    if overlap >= 2:
        # aplica crossfade keyframes (video + volume si existieran)
        _apply_crossfade_keyframes(left, right, overlap)
    else:
        # corte duro -> limpiar keyframes para asegurar que no hay transiciones a medias
        _clear_crossfade_keyframes([left, right])

    # limpiar contexto y estado
    if 'multicam_context' in state.control_state:
        del state.control_state['multicam_context']
    state.control_state.setdefault('active_tools', set()).discard('camera')

    try:
        bpy.ops.sequencer.refresh_all()
    except Exception:
        pass


# ----------------------------
# Handler /CAM/N (press/release)
# ----------------------------
def handle_cam_index(address, args):
    """
    address like "/CAM/1" ; args: [1] press, [0] release
    Press: activa herramienta y realiza bind + split (auto_cut toggled via state)
    Release: finaliza la operación (aplica crossfade si correspondiera)
    """
    try:
        parts = address.strip("/").split("/")
        if len(parts) >= 2 and parts[0].upper() == "CAM":
            idx = int(parts[1])
        else:
            return
    except Exception:
        return

    if not args or not isinstance(args[0], (bool, int, float)):
        return

    is_pressed = bool(args[0])

    # Release -> finalizar
    if not is_pressed:
        # finalize multicam interactive if exists
        _finalize_camera_cut()
        print("bl_cam: CAM release -> finalized and tool deactivated")
        return

    # Press -> activar herramienta camera (tool mode)
    state.control_state.setdefault('active_tools', set()).add('camera')

    scene_vse = bpy.context.scene
    active_strip = getattr(scene_vse.sequence_editor, "active_strip", None)
    if not active_strip or active_strip.type != 'SCENE' or not active_strip.scene:
        print("bl_cam.handle_cam_index: No active SCENE strip.")
        return

    source_scene = active_strip.scene
    cameras = build_camera_map_for_scene(source_scene)
    if not cameras:
        print("bl_cam.handle_cam_index: No cameras in source scene.")
        return

    idx_clamped = max(1, min(len(cameras), idx))
    target_camera = cameras[idx_clamped - 1]

    auto_cut = state.control_state.get("auto_cut", False)
    split_frame = scene_vse.frame_current

    # if there is an existing multicam_context, finalize it before starting a new one
    if 'multicam_context' in state.control_state:
        _finalize_camera_cut()

    result = perform_bind_and_split(active_strip, target_camera, split_frame, auto_cut=auto_cut)
    if result:
        print(f"bl_cam: CAM/{idx} -> bound. info: {result}")


# ----------------------------
# Multicam overlap (jog + nudge)
# ----------------------------

def _perform_multicam_overlap_from_jog(jog_value):
    """
    Movimiento progresivo con jog durante multicam.
    Jog negativo = overlap (crossfade), jog positivo = gap.
    """
    if 'camera' not in state.control_state.get('active_tools', set()):
        return

    context = state.control_state.get('multicam_context')
    if not context:
        return

    # Sensibilidad: jog_value ∈ [-1, 1], lo escalamos a frames
    delta = int(round(jog_value * 5.0))  # ajustar factor si es muy rápido/lento
    _perform_multicam_overlap_movement(delta)


def _perform_multicam_overlap_from_nudge(direction):
    """
    Movimiento discreto con /Pstrip (direction=-1) y /Nstrip (direction=+1).
    """
    if 'camera' not in state.control_state.get('active_tools', set()):
        return

    context = state.control_state.get('multicam_context')
    if not context:
        return

    delta = int(direction)  # siempre ±1 frame
    _perform_multicam_overlap_movement(delta)


def _perform_multicam_overlap_movement(delta_frames):
    """
    Lógica central de movimiento de overlap/gap en multicam.
    Mueve el right_strip en su canal seguro.
    """
    context = state.control_state.get('multicam_context')
    sequencer = bpy.context.scene.sequence_editor
    if not context or not sequencer:
        return

    right_name = context.get('right_strip_name')
    if not right_name:
        return

    right_strip = sequencer.sequences_all.get(right_name)
    if not right_strip:
        return

    # Aplicar movimiento
    right_strip.frame_start += delta_frames

    # Opcional: seguir con el cabezal si la navegación lo pide
    if state.control_state.get('strip_nav_follow_active', False):
        target_frame = max(bpy.context.scene.frame_start, right_strip.frame_final_start - 1)
        bpy.context.scene.frame_current = target_frame


# ----------------------------
# Resync / rebuild DB
# ----------------------------
def rebuild_database_from_vse():
    data = {}
    scene_vse = bpy.context.scene
    if not scene_vse.sequence_editor:
        save_camera_data(data)
        return data
    for s in scene_vse.sequence_editor.sequences_all:
        if s.type != 'SCENE' or not s.scene:
            continue
        ensure_strip_uuid(s)
        u = get_strip_uuid(s)
        scene_frame = map_vse_frame_to_scene_frame(s, scene_vse.frame_current)
        cam_name = None
        try:
            markers = [m for m in s.scene.timeline_markers if m.frame == scene_frame and getattr(m, "camera", None)]
            if markers:
                cam_name = markers[-1].camera.name
            elif getattr(s.scene, "camera", None):
                cam_name = s.scene.camera.name
        except Exception:
            cam_name = None
        if u and cam_name:
            data[u] = cam_name
    save_camera_data(data)
    print("bl_cam.rebuild_database_from_vse: rebuild complete.")
    return data

@persistent
def resync_on_undo(dummy):
    try:
        rebuild_database_from_vse()
    except Exception as e:
        print("bl_cam.resync_on_undo error", e)


# ----------------------------
# Register helpers
# ----------------------------
def register_handlers():
    if resync_on_undo not in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.append(resync_on_undo)
    if resync_on_undo not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(resync_on_undo)

def unregister_handlers():
    if resync_on_undo in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(resync_on_undo)
    if resync_on_undo in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(resync_on_undo)

def register_actions():
    """
    Registrar los hooks para jog / plus-minus. Llamar desde __init__.register o osc_server.register.
    """
    state.jog_actions['camera'] = _perform_camera_from_jog
    state.plus_minus_actions['camera'] = _perform_camera_from_nudge

def unregister_actions():
    state.jog_actions.pop('camera', None)
    state.plus_minus_actions.pop('camera', None)
