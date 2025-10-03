# groups_logic.py

"""
Módulo central para toda la lógica de agrupado de strips en el VSE.
Implementa la "Regla Simple": Set Group siempre destruye los grupos
antiguos implicados y crea uno nuevo a partir de la selección.

Añadidos:
 - run_auto_mirror_check(modified_strips)
 - auto_mirror_birth(new_strips)
 - auto_mirror_birth_from_cut(new_strips)  # NUEVO: agrupado directo post-corte RIGHT
 - helpers internos mínimos para crear/destrozar grupos y persistir.
"""

import bpy
import json
import uuid
from . import state  # para actualizar last_group_id si se desea

GROUPS = {}
EXCLUSIONS = {}

def _get_storage_property():
    return bpy.context.scene.get("vse_osc_groups_json", "")

def _set_storage_property(json_string):
    bpy.context.scene["vse_osc_groups_json"] = json_string

def _save_data_to_scene():
    storage_data = {"groups": GROUPS, "exclusions": EXCLUSIONS}
    try:
        json_string = json.dumps(storage_data, indent=2)
        _set_storage_property(json_string)
        print("Datos de grupos guardados en la escena.")
    except TypeError as e:
        print(f"Error al serializar los datos de grupos a JSON: {e}")

def _load_data_from_scene():
    global GROUPS, EXCLUSIONS
    json_string = _get_storage_property()
    if not json_string:
        GROUPS, EXCLUSIONS = {}, {}
        return

    try:
        storage_data = json.loads(json_string)
        GROUPS = storage_data.get("groups", {})
        EXCLUSIONS = storage_data.get("exclusions", {})
        print("Datos de grupos cargados desde la escena.")
    except json.JSONDecodeError:
        print("Error: No se pudo decodificar el JSON de grupos. Se usarán datos vacíos.")
        GROUPS, EXCLUSIONS = {}, {}
        return

    if not bpy.context.scene.sequence_editor: return
    all_strip_names = {s.name for s in bpy.context.scene.sequence_editor.sequences_all}
    
    groups_to_delete = []
    for group_id, members in list(GROUPS.items()):
        GROUPS[group_id] = [name for name in members if name in all_strip_names]
        if len(GROUPS[group_id]) < 2:
            groups_to_delete.append(group_id)
    for group_id in groups_to_delete:
        if group_id in GROUPS: del GROUPS[group_id]

    exclusions_to_delete = []
    for strip_name, excluded_partners in list(EXCLUSIONS.items()):
        if strip_name not in all_strip_names:
            exclusions_to_delete.append(strip_name)
        else:
            EXCLUSIONS[strip_name] = [name for name in excluded_partners if name in all_strip_names]
    for strip_name in exclusions_to_delete:
        if strip_name in EXCLUSIONS: del EXCLUSIONS[strip_name]

def init_group_system():
    _load_data_from_scene()
    update_known_strips_registry()

def set_group_from_selection(selection_objects):
    """
    Acción CONSTRUCTIVA para 'Set Group' bajo la "Regla Simple".
    1. Destruye cualquier grupo al que pertenezcan los strips de entrada.
    2. Crea un único grupo nuevo con exactamente esos strips.
    3. Devuelve la información del nuevo grupo para la auto-selección.
    """
    if not selection_objects or len(selection_objects) < 2:
        print("Se necesitan al menos 2 strips para formar un grupo.")
        return None

    bpy.ops.ed.undo_push(message="OSC Set Group")
    
    working_set_names = {s.name for s in selection_objects}

    # Encontrar y destruir todos los grupos antiguos implicados
    involved_groups_ids = set()
    for group_id, members in GROUPS.items():
        if not working_set_names.isdisjoint(set(members)):
            involved_groups_ids.add(group_id)
    
    for group_id in involved_groups_ids:
        if group_id in GROUPS: del GROUPS[group_id]
        
    # Crear el nuevo grupo
    new_group_id = _create_group_id()
    GROUPS[new_group_id] = list(working_set_names)
    print(f"Nuevo grupo creado '{new_group_id}' con {len(working_set_names)} miembros.")

    # Limpiar exclusiones internas del nuevo grupo
    for member_a in working_set_names:
        for member_b in working_set_names:
            if member_a != member_b:
                _remove_exclusion(member_a, member_b)
                
    _save_data_to_scene()
    
    # actualizar last_group_id en state si existe
    try:
        state.control_state['last_group_id'] = new_group_id
    except Exception:
        pass
    
    # Punto de registro centralizado al crear/modificar grupo
    update_known_strips_registry()

    return {'id': new_group_id, 'members': list(working_set_names)}

def ungroup_from_selection(selection):
    if not selection: return
    
    bpy.ops.ed.undo_push(message="OSC Ungroup")
    selected_names = {s.name for s in selection}

    groups_to_modify = {}
    for group_id, members in list(GROUPS.items()):
        members_to_remove = selected_names.intersection(set(members))
        if members_to_remove:
            groups_to_modify[group_id] = members_to_remove
            
    if not groups_to_modify:
        print("Ninguno de los strips seleccionados pertenecía a un grupo.")
        return

    for group_id, members_to_remove in groups_to_modify.items():
        original_members = set(GROUPS[group_id])
        members_to_keep = original_members - members_to_remove
        
        for removed_name in members_to_remove:
            for kept_name in members_to_keep:
                _add_exclusion(removed_name, kept_name)
        
        if len(members_to_keep) < 2:
            if group_id in GROUPS: del GROUPS[group_id]
            print(f"Grupo '{group_id}' disuelto por tener menos de 2 miembros.")
        else:
            GROUPS[group_id] = list(members_to_keep)
            print(f"{len(members_to_remove)} miembros sacados del grupo '{group_id}'.")
            
    _save_data_to_scene()

def expand_selection_to_groups():
    if not bpy.context.selected_sequences: return
    initial_selection_names = {s.name for s in bpy.context.selected_sequences}
    final_selection_names = set(initial_selection_names)

    for group_id, members in GROUPS.items():
        member_set = set(members)
        if not initial_selection_names.isdisjoint(member_set):
            final_selection_names.update(member_set)
    
    for strip in bpy.context.scene.sequence_editor.sequences_all:
        strip.select = strip.name in final_selection_names

# --- NUEVO: Lógica del Registro de Strips y Agrupado desde Nuevos ---

def update_known_strips_registry():
    """
    Escanea el VSE y actualiza el registro de 'known_strip_names' en el estado.
    """
    if not bpy.context.scene or not bpy.context.scene.sequence_editor:
        state.control_state['known_strip_names'] = set()
        return
    
    all_names = {s.name for s in bpy.context.scene.sequence_editor.sequences_all}
    state.control_state['known_strip_names'] = all_names
    print(f"Registro de strips actualizado. {len(all_names)} strips conocidos.")


def register_specific_strips(strips_to_register):
    """
    Añade una lista específica de strips al registro de 'known_strip_names'.
    """
    if not strips_to_register:
        return
    names_to_add = {s.name for s in strips_to_register}
    state.control_state['known_strip_names'].update(names_to_add)
    print(f"Registro específico: {len(names_to_add)} strips añadidos al registro.")


def handle_group_from_new(address, args):
    """
    Trigger para buscar strips no registrados y intentar agruparlos
    usando la lógica de auto-mirror.
    """
    if not args or not args[0]: return

    print("\n--- INICIANDO AGRUPADO DESDE NUEVOS STRIPS ---")
    if not bpy.context.scene or not bpy.context.scene.sequence_editor:
        return

    bpy.ops.ed.undo_push(message="OSC Group from New")

    all_current_strips = list(bpy.context.scene.sequence_editor.sequences_all)
    known_names = state.control_state.get('known_strip_names', set())
    new_strip_names = {s.name for s in all_current_strips} - known_names

    if not new_strip_names:
        print("No se encontraron strips nuevos para procesar.")
        return

    print(f"Strips nuevos encontrados: {list(new_strip_names)}")
    new_strips_objects = [s for s in all_current_strips if s.name in new_strip_names]

    for new_strip in new_strips_objects:
        run_auto_mirror_check([new_strip])

    # Registro final para "sellar" a todos los strips como conocidos.
    update_known_strips_registry()
    print("--- AGRUPADO DESDE NUEVOS FINALIZADO ---\n")

# -------------------- AUTO MIRROR (existente) --------------------

def _create_group_id():
    return f"vse_osc_group_{uuid.uuid4().hex}"

def _get_strip_visible_range(strip):
    """Devuelve (start, end) visibles en timeline (frame_final_start/end preferido)."""
    if hasattr(strip, "frame_final_start") and hasattr(strip, "frame_final_end"):
        return int(strip.frame_final_start), int(strip.frame_final_end)
    else:
        start = int(strip.frame_start)
        end = int(strip.frame_start + getattr(strip, "frame_duration", getattr(strip, "frame_final_duration", 0)))
        return start, end

def _get_group_bounds(group_members):
    """Dado una lista de strip names (miembros del grupo), devuelve min_start, max_end, min_channel, max_channel."""
    seqs = bpy.context.scene.sequence_editor.sequences_all if bpy.context.scene.sequence_editor else []
    members = [s for s in seqs if s.name in set(group_members)]
    if not members:
        return None
    starts = []
    ends = []
    chans = []
    for s in members:
        st, ed = _get_strip_visible_range(s)
        starts.append(st); ends.append(ed); chans.append(int(s.channel))
    return min(starts), max(ends), min(chans), max(chans)

def _strips_from_names(names):
    seqs = bpy.context.scene.sequence_editor.sequences_all if bpy.context.scene.sequence_editor else []
    return [s for s in seqs if s.name in set(names)]

def _destroy_groups_involving(strip_names):
    """Borra todos los grupos que contienen cualquiera de strip_names."""
    involved = []
    for gid, members in list(GROUPS.items()):
        if not set(members).isdisjoint(set(strip_names)):
            involved.append(gid)
    for gid in involved:
        if gid in GROUPS: del GROUPS[gid]

def _create_group_from_strips(strip_objs):
    """Crea un grupo nuevo a partir de objetos de strip. Borra grupos anteriores que impliquen los strips."""
    if not strip_objs or len(strip_objs) < 2:
        return None
    names = [s.name for s in strip_objs]
    _destroy_groups_involving(names)
    gid = _create_group_id()
    GROUPS[gid] = list(names)
    _save_data_to_scene()
    try:
        state.control_state['last_group_id'] = gid
    except Exception:
        pass

    # Auto-selección opcional
    try:
        if state.control_state.get('auto_select_last_grouped', False):
            for s in bpy.context.scene.sequence_editor.sequences_all:
                s.select = False
            for name in GROUPS[gid]:
                strip_obj = bpy.context.scene.sequence_editor.sequences_all.get(name)
                if strip_obj:
                    strip_obj.select = True
            first = GROUPS[gid][0] if GROUPS[gid] else None
            if first and bpy.context.scene.sequence_editor:
                bpy.context.scene.sequence_editor.active_strip = bpy.context.scene.sequence_editor.sequences_all.get(first)
    except Exception as e:
        print(f"AUTO SELECT: fallo intentando seleccionar grupo '{gid}': {e}")

    # Punto de registro centralizado al crear el grupo
    update_known_strips_registry()
    
    return gid

def _is_excluded_pair(a_name, b_name):
    """Comprueba exclusión bidireccional."""
    if a_name in EXCLUSIONS and b_name in EXCLUSIONS[a_name]:
        return True
    if b_name in EXCLUSIONS and a_name in EXCLUSIONS[b_name]:
        return True
    return False

def run_auto_mirror_check(modified_strips):
    """
    (se mantiene tal cual — no forma parte del flujo simple post-corte RIGHT)
    """
    if not modified_strips: return
    if not bpy.context.scene or not bpy.context.scene.sequence_editor:
        return

    fps = bpy.context.scene.render.fps if hasattr(bpy.context.scene.render, "fps") else 24
    tol_seconds = float(state.control_state.get("mirror_tolerance_sec", 0.0))
    tol_frames = int(round(tol_seconds * fps))
    chan_range = int(state.control_state.get("mirror_channel_range", 1))

    seqs_all = list(bpy.context.scene.sequence_editor.sequences_all)

    def _find_matching_strips(target_strip, tol_frames, chan_range):
        matches = []
        t_st, t_ed = _get_strip_visible_range(target_strip)
        t_chan = int(getattr(target_strip, "channel", 0))
        for s in seqs_all:
            if s.name == target_strip.name:
                continue
            if _is_excluded_pair(target_strip.name, s.name):
                continue
            s_st, s_ed = _get_strip_visible_range(s)
            if abs(s_st - t_st) <= tol_frames and abs(s_ed - t_ed) <= tol_frames:
                if abs(int(s.channel) - t_chan) <= chan_range:
                    matches.append(s)
        return matches

    def _get_group_bounds_safe(gid):
        members = GROUPS.get(gid, [])
        if not members: return None
        return _get_group_bounds(members)

    groups_snapshot = list(GROUPS.items())

    for mod_strip in modified_strips:
        try:
            mod_name = mod_strip.name
        except Exception:
            continue

        mod_start, mod_end = _get_strip_visible_range(mod_strip)
        tol = tol_frames
        mod_chan = int(getattr(mod_strip, "channel", 0))

        new_group_created = False
        created_gid = None

        for gid, members in groups_snapshot:
            bounds = _get_group_bounds_safe(gid)
            if not bounds: continue
            grp_min_start, grp_max_end, grp_min_chan, grp_max_chan = bounds

            if grp_min_start >= (mod_start - tol) and grp_max_end <= (mod_end + tol):
                seqs_all_local = bpy.context.scene.sequence_editor.sequences_all
                member_objs = [s for s in seqs_all_local if s.name in set(members)]
                matched = False
                for m in member_objs:
                    if abs(int(m.channel) - mod_chan) <= int(state.control_state.get("mirror_channel_range", 1)):
                        if not _is_excluded_pair(mod_name, m.name):
                            matched = True
                            break
                if not matched:
                    continue

                member_objs = [s for s in seqs_all_local if s.name in set(members)]
                new_group_members_names = list({m.name for m in member_objs} | {mod_name})
                objs = _strips_from_names(new_group_members_names)
                if len(objs) >= 2:
                    created_gid = _create_group_from_strips(objs)
                    print(f"AUTO MIRROR: creado grupo '{created_gid}' a partir de modificado '{mod_name}' y grupo '{gid}'")
                    new_group_created = True
                break

        if not new_group_created:
            matches = _find_matching_strips(mod_strip, tol_frames, int(state.control_state.get("mirror_channel_range", 1)))
            if matches:
                objs = [mod_strip] + matches
                created_gid = _create_group_from_strips(objs)
                if created_gid:
                    print(f"AUTO MIRROR: creado grupo '{created_gid}' por coincidencia strip↔strip para '{mod_name}' con {len(objs)} miembros.")
                    new_group_created = True

        # No se ejecuta la expansión en este flujo simplificado.

    return

def auto_mirror_birth(new_strips):
    """
    new_strips: lista de strip objects recién creados por un corte (split).
    Lógica: agrupar aquellos que comparten frame_final_start exactamente (lugar del corte).
    (Se mantiene para compatibilidad; no es la ruta del nuevo flujo RIGHT simplificado).
    """
    if not new_strips:
        return

    if not bpy.context.scene or not bpy.context.scene.sequence_editor:
        return

    by_start = {}
    for s in new_strips:
        st, ed = _get_strip_visible_range(s)
        by_start.setdefault(st, []).append(s)

    for start_frame, strips_at_start in by_start.items():
        if len(strips_at_start) < 2:
            continue
        valid = []
        for s in strips_at_start:
            ok = True
            for t in strips_at_start:
                if s is t: continue
                if _is_excluded_pair(s.name, t.name):
                    ok = False
                    break
            if ok:
                valid.append(s)
        if len(valid) < 2:
            continue
        gid = _create_group_from_strips(valid)
        print(f"AUTO BIRTH: creado grupo '{gid}' en start={start_frame} con {len(valid)} miembros.")

# -------------------- NUEVO: AUTO MIRROR (post-corte RIGHT simplificado) --------------------

def auto_mirror_birth_from_cut(new_strips):
    """
    Agrupa DIRECTAMENTE todos los strips nacidos del corte (lado RIGHT).
    - No se compara con grupos/strips antiguos.
    - Se deshacen exclusiones internas entre los nuevos.
    - Se guarda last_group_id para selección posterior (ya lo hace _create_group_from_strips).
    - Se registran los nombres de los nuevos strips en state.control_state['last_cut_right_registered'].
    """
    if not new_strips or len(new_strips) < 2:
        # Registrar de todas formas qué nació, aunque no alcance para grupo
        try:
            state.control_state['last_cut_right_registered'] = [s.name for s in (new_strips or [])]
        except Exception:
            pass
        return

    # Limpiar exclusiones internas entre los nuevos
    names = [s.name for s in new_strips]
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            _remove_exclusion(names[i], names[j])

    gid = _create_group_from_strips(new_strips)
    print(f"AUTO CUT RIGHT: creado grupo '{gid}' con {len(new_strips)} miembros (post-corte).")

    # Registrar los strips nacidos del corte RIGHT
    try:
        state.control_state['last_cut_right_registered'] = names
    except Exception:
        pass

# -------------------- FIN: AUTO MIRROR --------------------

def _add_exclusion(strip_a_name, strip_b_name):
    EXCLUSIONS.setdefault(strip_a_name, []).append(strip_b_name)
    EXCLUSIONS[strip_a_name] = list(set(EXCLUSIONS[strip_a_name]))
    EXCLUSIONS.setdefault(strip_b_name, []).append(strip_a_name)
    EXCLUSIONS[strip_b_name] = list(set(EXCLUSIONS[strip_b_name]))

def _remove_exclusion(strip_a_name, strip_b_name):
    if strip_a_name in EXCLUSIONS and strip_b_name in EXCLUSIONS[strip_a_name]:
        EXCLUSIONS[strip_a_name].remove(strip_b_name)
    if strip_b_name in EXCLUSIONS and strip_a_name in EXCLUSIONS[strip_b_name]:
        EXCLUSIONS[strip_b_name].remove(strip_a_name)

def register():
    if not hasattr(bpy.types.Scene, 'vse_osc_groups_json'):
        bpy.types.Scene.vse_osc_groups_json = bpy.props.StringProperty(name="VSE OSC Groups JSON Storage")

def unregister():
    if hasattr(bpy.types.Scene, 'vse_osc_groups_json'):
        del bpy.types.Scene.vse_osc_groups_json