# tools_extra.py

import bpy
import math
from . import state
from . import osc_feedback
from . import config

# --- Estados Internos de las Herramientas ---
zoom_snap_state = { 'snapped_out': False, 'snapped_in': False }
position_snap_state = {
    'posx_snapped_out': False, 'posx_snapped_in': False,
    'posy_snapped_out': False, 'posy_snapped_in': False,
}
rotation_snap_state = { 'snapped_out': False, 'snapped_in': False }
origin_snap_state = {
    'origx_snapped_out': False, 'origx_snapped_in': False,
    'origy_snapped_out': False, 'origy_snapped_in': False,
}

toggle_tool_state = {
    'mirror_x': {'last_jog_sign': 0},
    'mirror_y': {'last_jog_sign': 0},
    'reverse': {'last_jog_sign': 0},
}

color_snap_state = {
    'saturation': {'snapped_out': False, 'snapped_in': False},
    'multiply': {'snapped_out': False, 'snapped_in': False},
}

def reset_all_snap_states():
    """Reinicia todos los estados de snap y de las herramientas de toggle."""
    global zoom_snap_state, position_snap_state, rotation_snap_state, origin_snap_state, color_snap_state
    zoom_snap_state = { 'snapped_out': False, 'snapped_in': False }
    position_snap_state = {
        'posx_snapped_out': False, 'posx_snapped_in': False,
        'posy_snapped_out': False, 'posy_snapped_in': False,
    }
    rotation_snap_state = { 'snapped_out': False, 'snapped_in': False }
    origin_snap_state = {
        'origx_snapped_out': False, 'origx_snapped_in': False,
        'origy_snapped_out': False, 'origy_snapped_in': False,
    }
    for tool in toggle_tool_state:
        toggle_tool_state[tool]['last_jog_sign'] = 0
    for tool in color_snap_state:
        color_snap_state[tool]['snapped_out'] = False
        color_snap_state[tool]['snapped_in'] = False

# --- Funciones Auxiliares ---
def _get_selected_strips():
    return [s for s in bpy.context.selected_sequences if s.select and hasattr(s, 'transform')]

def _get_selected_strips_alpha():
    return [s for s in bpy.context.selected_sequences if s.select and hasattr(s, 'blend_alpha')]

def _get_color_compatible_strips():
    """Devuelve strips que soportan ajustes de color"""
    return [s for s in bpy.context.selected_sequences if s.select and hasattr(s, 'color_saturation')]

def _tag_vse_redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'SEQUENCE_EDITOR':
                area.tag_redraw()

def _auto_record_insert_key(target, data_path):
    """Inserta keyframe si auto_record está activo."""
    if not state.control_state.get('auto_record', False):
        return
    frame = bpy.context.scene.frame_current
    try:
        target.keyframe_insert(data_path=data_path, frame=frame, options={'INSERTKEY_NEEDED'})
    except (TypeError, RuntimeError):
        pass

def _perform_zoom_continuous(delta):
    strips = _get_selected_strips()
    if not strips: return
    for strip in strips:
        new_scale = strip.transform.scale_x + delta
        strip.transform.scale_x = new_scale
        strip.transform.scale_y = new_scale
        _auto_record_insert_key(strip.transform, 'scale_x')
        _auto_record_insert_key(strip.transform, 'scale_y')

def _perform_zoom_with_snap(delta):
    strips = _get_selected_strips()
    if not strips: return
    use_snap = state.control_state.get('use_snap_limit', False)
    if use_snap:
        snap_value = bpy.context.scene.osc_vse_properties.zoom_snap_value
        for strip in strips:
            if (delta < 0 and zoom_snap_state['snapped_out']) or \
               (delta > 0 and zoom_snap_state['snapped_in']):
                continue
            current_scale = strip.transform.scale_x
            new_scale = current_scale + delta
            if delta < 0 and current_scale > snap_value and new_scale <= snap_value:
                new_scale = snap_value
                zoom_snap_state['snapped_out'] = True
            elif delta > 0 and current_scale < snap_value and new_scale >= snap_value:
                new_scale = snap_value
                zoom_snap_state['snapped_in'] = True
            strip.transform.scale_x = new_scale
            strip.transform.scale_y = new_scale
            _auto_record_insert_key(strip.transform, 'scale_x')
            _auto_record_insert_key(strip.transform, 'scale_y')
    else:
        for strip in strips:
            new_scale = strip.transform.scale_x + delta
            strip.transform.scale_x = new_scale
            strip.transform.scale_y = new_scale
            _auto_record_insert_key(strip.transform, 'scale_x')
            _auto_record_insert_key(strip.transform, 'scale_y')

def _perform_zoom_from_plus_minus(direction):
    sensitivity = config.PLUS_MINUS_SENSITIVITY
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = direction * sensitivity
    _perform_zoom_continuous(delta)

def _perform_zoom_from_jog(jog_value):
    sensitivity = config.JOG_SENSITIVITY
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = jog_value * sensitivity
    _perform_zoom_with_snap(delta)

def _handle_zoom_keyframe(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        strip.transform.keyframe_insert(data_path='scale_x', frame=frame)
        strip.transform.keyframe_insert(data_path='scale_y', frame=frame)
    _tag_vse_redraw()

def _handle_zoom_delete(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try:
            strip.transform.keyframe_delete(data_path='scale_x', frame=frame)
            strip.transform.keyframe_delete(data_path='scale_y', frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _perform_position_x_continuous(delta):
    for strip in _get_selected_strips():
        strip.transform.offset_x += delta
        _auto_record_insert_key(strip.transform, 'offset_x')

def _perform_position_y_continuous(delta):
    for strip in _get_selected_strips():
        strip.transform.offset_y += delta
        _auto_record_insert_key(strip.transform, 'offset_y')

def _perform_position_x_with_snap(delta):
    use_snap = state.control_state.get('use_snap_limit', False)
    if use_snap:
        snap_value = bpy.context.scene.osc_vse_properties.position_x_snap_value
        for strip in _get_selected_strips():
            if (delta < 0 and position_snap_state['posx_snapped_out']) or \
               (delta > 0 and position_snap_state['posx_snapped_in']):
                continue
            current_pos = strip.transform.offset_x
            new_pos = current_pos + delta
            if current_pos > snap_value and new_pos <= snap_value:
                new_pos = snap_value
                position_snap_state['posx_snapped_out'] = True
            elif current_pos < snap_value and new_pos >= snap_value:
                new_pos = snap_value
                position_snap_state['posx_snapped_in'] = True
            strip.transform.offset_x = new_pos
            _auto_record_insert_key(strip.transform, 'offset_x')
    else:
        for strip in _get_selected_strips():
            strip.transform.offset_x += delta
            _auto_record_insert_key(strip.transform, 'offset_x')

def _perform_position_y_with_snap(delta):
    use_snap = state.control_state.get('use_snap_limit', False)
    if use_snap:
        snap_value = bpy.context.scene.osc_vse_properties.position_y_snap_value
        for strip in _get_selected_strips():
            if (delta < 0 and position_snap_state['posy_snapped_out']) or \
               (delta > 0 and position_snap_state['posy_snapped_in']):
                continue
            current_pos = strip.transform.offset_y
            new_pos = current_pos + delta
            if current_pos > snap_value and new_pos <= snap_value:
                new_pos = snap_value
                position_snap_state['posy_snapped_out'] = True
            elif current_pos < snap_value and new_pos >= snap_value:
                new_pos = snap_value
                position_snap_state['posy_snapped_in'] = True
            strip.transform.offset_y = new_pos
            _auto_record_insert_key(strip.transform, 'offset_y')
    else:
        for strip in _get_selected_strips():
            strip.transform.offset_y += delta
            _auto_record_insert_key(strip.transform, 'offset_y')

def _perform_position_x_from_plus_minus(direction):
    sensitivity = config.PLUS_MINUS_SENSITIVITY_POS
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = direction * sensitivity
    _perform_position_x_continuous(delta)

def _perform_position_y_from_plus_minus(direction):
    sensitivity = config.PLUS_MINUS_SENSITIVITY_POS
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = direction * sensitivity
    _perform_position_y_continuous(delta)

def _perform_position_x_from_jog(jog_value):
    sensitivity = config.JOG_SENSITIVITY_POS
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = jog_value * sensitivity
    _perform_position_x_with_snap(delta)

def _perform_position_y_from_jog(jog_value):
    sensitivity = config.JOG_SENSITIVITY_POS
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = jog_value * sensitivity
    _perform_position_y_with_snap(delta)

def _handle_position_keyframe(address, args, axis):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips: strip.transform.keyframe_insert(data_path=f'offset_{axis}', frame=frame)
    _tag_vse_redraw()

def _handle_position_delete(address, args, axis):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try: strip.transform.keyframe_delete(data_path=f'offset_{axis}', frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _perform_rotation_continuous(delta_degrees):
    delta_rad = math.radians(delta_degrees)
    for strip in _get_selected_strips():
        strip.transform.rotation += delta_rad
        _auto_record_insert_key(strip.transform, 'rotation')

def _perform_rotation_with_snap(delta_degrees):
    use_snap = state.control_state.get('use_snap_limit', False)
    if use_snap:
        snap_value_deg = bpy.context.scene.osc_vse_properties.rotation_snap_value
        snap_value_rad = math.radians(snap_value_deg)
        delta_rad = math.radians(delta_degrees)
        for strip in strips:
            if (delta_rad < 0 and rotation_snap_state['snapped_out']) or \
               (delta_rad > 0 and rotation_snap_state['snapped_in']):
                continue
            current_rot = strip.transform.rotation
            new_rot = current_rot + delta_rad
            if current_rot > snap_value_rad and new_rot <= snap_value_rad:
                new_rot = snap_value_rad
                rotation_snap_state['snapped_out'] = True
            elif current_rot < snap_value_rad and new_rot >= snap_value_rad:
                new_rot = snap_value_rad
                rotation_snap_state['snapped_in'] = True
            strip.transform.rotation = new_rot
            _auto_record_insert_key(strip.transform, 'rotation')
    else:
        delta_rad = math.radians(delta_degrees)
        for strip in _get_selected_strips():
            strip.transform.rotation += delta_rad
            _auto_record_insert_key(strip.transform, 'rotation')

def _perform_rotation_from_plus_minus(direction):
    sensitivity = config.PLUS_MINUS_SENSITIVITY_ROT
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    _perform_rotation_continuous(direction * sensitivity)

def _perform_rotation_from_jog(jog_value):
    sensitivity = config.JOG_SENSITIVITY_ROT
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    _perform_rotation_with_snap(jog_value * sensitivity)

def _handle_rotation_keyframe(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        strip.transform.keyframe_insert(data_path='rotation', frame=frame)
    _tag_vse_redraw()

def _handle_rotation_delete(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try:
            strip.transform.keyframe_delete(data_path='rotation', frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _perform_origin_continuous(delta, axis_index):
    for strip in _get_selected_strips():
        strip.transform.origin[axis_index] += delta
        _auto_record_insert_key(strip.transform, 'origin')

def _perform_origin_with_snap(delta, axis_index):
    use_snap = state.control_state.get('use_snap_limit', False)
    if use_snap:
        axis_name = 'x' if axis_index == 0 else 'y'
        snap_value = getattr(bpy.context.scene.osc_vse_properties, f'origin_{axis_name}_snap_value')
        snapped_out_key = f'orig{axis_name}_snapped_out'
        snapped_in_key = f'orig{axis_name}_snapped_in'
        for strip in _get_selected_strips():
            if (delta < 0 and origin_snap_state[snapped_out_key]) or \
               (delta > 0 and origin_snap_state[snapped_in_key]):
                continue
            current_pos = strip.transform.origin[axis_index]
            new_pos = current_pos + delta
            if current_pos > snap_value and new_pos <= snap_value:
                new_pos = snap_value
                origin_snap_state[snapped_out_key] = True
            elif current_pos < snap_value and new_pos >= snap_value:
                new_pos = snap_value
                origin_snap_state[snapped_in_key] = True
            strip.transform.origin[axis_index] = new_pos
            _auto_record_insert_key(strip.transform, 'origin')
    else:
        for strip in _get_selected_strips():
            strip.transform.origin[axis_index] += delta
            _auto_record_insert_key(strip.transform, 'origin')

def _perform_origin_from_plus_minus(direction, axis_index):
    sensitivity = config.PLUS_MINUS_SENSITIVITY_ORIG
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    _perform_origin_continuous(direction * sensitivity, axis_index)

def _perform_origin_from_jog(jog_value, axis_index):
    sensitivity = config.JOG_SENSITIVITY_ORIG
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    _perform_origin_with_snap(jog_value * sensitivity, axis_index)

def _handle_origin_keyframe(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        strip.transform.keyframe_insert(data_path='origin', frame=frame)
    _tag_vse_redraw()

def _handle_origin_delete(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try:
            strip.transform.keyframe_delete(data_path='origin', frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _perform_alpha_continuous(delta):
    for strip in _get_selected_strips_alpha():
        new_alpha = strip.blend_alpha + delta
        strip.blend_alpha = max(0.0, min(1.0, new_alpha))
        _auto_record_insert_key(strip, 'blend_alpha')

def _perform_alpha_from_plus_minus(direction):
    sensitivity = config.PLUS_MINUS_SENSITIVITY_ALPHA
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    _perform_alpha_continuous(direction * sensitivity)

def _perform_alpha_from_jog(jog_value):
    sensitivity = config.JOG_SENSITIVITY_ALPHA
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    _perform_alpha_continuous(jog_value * sensitivity)

def _handle_alpha_keyframe(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips_alpha(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        strip.keyframe_insert(data_path='blend_alpha', frame=frame)
    _tag_vse_redraw()

def _handle_alpha_delete(address, args):
    if not args or not args[0]: return
    strips, frame = _get_selected_strips_alpha(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try:
            strip.keyframe_delete(data_path='blend_alpha', frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _get_selected_crop_strips():
    return [s for s in bpy.context.selected_sequences if s.select and hasattr(s, 'crop')]

def _perform_crop_continuous(pixel_delta, property_name):
    strips = _get_selected_crop_strips()
    if not strips: return
    final_delta = int(round(pixel_delta))
    if final_delta == 0: return
    for strip in strips:
        strip_width, strip_height = 0, 0
        if hasattr(strip, 'elements') and strip.elements:
            strip_width, strip_height = strip.elements[0].orig_width, strip.elements[0].orig_height
        else:
            render = bpy.context.scene.render
            strip_width, strip_height = render.resolution_x, render.resolution_y
        current_pixels = getattr(strip.crop, property_name)
        new_pixels = current_pixels + final_delta
        new_pixels = max(0, new_pixels)
        if property_name == 'min_x': new_pixels = min(new_pixels, strip_width - strip.crop.max_x)
        elif property_name == 'max_x': new_pixels = min(new_pixels, strip_width - strip.crop.min_x)
        elif property_name == 'min_y': new_pixels = min(new_pixels, strip_height - strip.crop.max_y)
        elif property_name == 'max_y': new_pixels = min(new_pixels, strip_height - strip.crop.min_y)
        setattr(strip.crop, property_name, new_pixels)
        _auto_record_insert_key(strip.crop, property_name)

def _perform_crop_from_plus_minus(direction, crop_side):
    prop_map = {'left': 'min_x', 'right': 'max_x', 'top': 'max_y', 'bottom': 'min_y'}
    inversion_map = {'left': config.CROP_L_INVERT, 'right': config.CROP_R_INVERT, 'top': config.CROP_T_INVERT, 'bottom': config.CROP_B_INVERT}
    if inversion_map.get(crop_side, False): direction *= -1
    property_name = prop_map[crop_side]
    sensitivity = config.PLUS_MINUS_SENSITIVITY_CROP_PX
    if state.control_state['shift_active']: sensitivity = 1
    _perform_crop_continuous(direction * sensitivity, property_name)

def _perform_crop_from_jog(jog_value, crop_side):
    prop_map = {'left': 'min_x', 'right': 'max_x', 'top': 'max_y', 'bottom': 'min_y'}
    inversion_map = {'left': config.CROP_L_INVERT, 'right': config.CROP_R_INVERT, 'top': config.CROP_T_INVERT, 'bottom': config.CROP_B_INVERT}
    if inversion_map.get(crop_side, False): jog_value *= -1
    property_name = prop_map[crop_side]
    sensitivity = config.JOG_SENSITIVITY_CROP_PX
    if state.control_state['shift_active']: sensitivity /= config.PRECISION_MODE_DIVISOR
    pixel_delta = jog_value * sensitivity
    _perform_crop_continuous(pixel_delta, property_name)

def _handle_crop_keyframe(address, args, crop_side):
    if not args or not args[0]: return
    prop_map = {'left': 'min_x', 'right': 'max_x', 'top': 'max_y', 'bottom': 'min_y'}
    property_name = prop_map[crop_side]
    strips, frame = _get_selected_crop_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        strip.crop.keyframe_insert(data_path=property_name, frame=frame)
    _tag_vse_redraw()

def _handle_crop_delete(address, args, crop_side):
    if not args or not args[0]: return
    prop_map = {'left': 'min_x', 'right': 'max_x', 'top': 'max_y', 'bottom': 'min_y'}
    property_name = prop_map[crop_side]
    strips, frame = _get_selected_crop_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try:
            strip.crop.keyframe_delete(data_path=property_name, frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _get_blend_compatible_strips():
    return [s for s in bpy.context.selected_sequences if s.select and hasattr(s, 'bl_rna') and 'blend_type' in s.bl_rna.properties]

def _handle_blend_keyframe(address, args):
    if not args or not args[0]: return
    strips, frame = _get_blend_compatible_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips: strip.keyframe_insert(data_path='blend_type', frame=frame)
    _tag_vse_redraw()

def _handle_blend_delete(address, args):
    if not args or not args[0]: return
    strips, frame = _get_blend_compatible_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try: strip.keyframe_delete(data_path='blend_type', frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def _perform_boolean_toggle(property_name):
    strips = bpy.context.selected_sequences
    if not strips: return
    bpy.ops.ed.undo_push(message=f"OSC Toggle {property_name}")
    for strip in strips:
        if hasattr(strip, property_name):
            current_value = getattr(strip, property_name)
            setattr(strip, property_name, not current_value)
    _tag_vse_redraw()

def _perform_toggle_from_plus_minus(tool_name):
    property_map = {
        'mirror_x': 'use_flip_x',
        'mirror_y': 'use_flip_y',
        'reverse': 'use_reverse_frames',
    }
    prop_name = property_map.get(tool_name)
    if prop_name:
        _perform_boolean_toggle(prop_name)

def _perform_toggle_from_jog(jog_value, tool_name):
    property_map = {
        'mirror_x': 'use_flip_x',
        'mirror_y': 'use_flip_y',
        'reverse': 'use_reverse_frames',
    }
    prop_name = property_map.get(tool_name)
    if not prop_name: return

    current_sign = 0
    if jog_value > 0.01: current_sign = 1
    elif jog_value < -0.01: current_sign = -1

    last_sign = toggle_tool_state[tool_name].get('last_jog_sign', 0)

    if current_sign != last_sign:
        if current_sign != 0:
            _perform_boolean_toggle(prop_name)
        toggle_tool_state[tool_name]['last_jog_sign'] = current_sign

def _handle_boolean_keyframe(address, args, property_name):
    if not args or not args[0]: return
    strips, frame = bpy.context.selected_sequences, bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        if hasattr(strip, property_name):
            strip.keyframe_insert(data_path=property_name, frame=frame)
    _tag_vse_redraw()

def _handle_boolean_delete(address, args, property_name):
    if not args or not args[0]: return
    strips, frame = bpy.context.selected_sequences, bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        if hasattr(strip, property_name):
            try:
                strip.keyframe_delete(data_path=property_name, frame=frame)
            except RuntimeError: pass
    _tag_vse_redraw()

def _perform_color_continuous(delta, property_name, min_val, max_val):
    strips = _get_color_compatible_strips()
    if not strips: return

    for strip in strips:
        current_val = getattr(strip, property_name)
        new_val = current_val + delta
        setattr(strip, property_name, max(min_val, min(max_val, new_val)))
        _auto_record_insert_key(strip, property_name)

def _perform_color_with_snap(delta, tool_name, property_name, min_val, max_val):
    strips = _get_color_compatible_strips()
    if not strips: return

    use_snap = state.control_state.get('use_snap_limit', False)
    snap_value = 1.0

    if use_snap:
        snap_state = color_snap_state[tool_name]
        for strip in strips:
            if (delta < 0 and snap_state['snapped_out']) or \
               (delta > 0 and snap_state['snapped_in']):
                continue

            current_val = getattr(strip, property_name)
            new_val = current_val + delta

            if delta < 0 and current_val > snap_value and new_val <= snap_value:
                new_val = snap_value
                snap_state['snapped_out'] = True
            elif delta > 0 and current_val < snap_value and new_val >= snap_value:
                new_val = snap_value
                snap_state['snapped_in'] = True

            setattr(strip, property_name, max(min_val, min(max_val, new_val)))
            _auto_record_insert_key(strip, property_name)
    else:
        for strip in strips:
            current_val = getattr(strip, property_name)
            new_val = current_val + delta
            setattr(strip, property_name, max(min_val, min(max_val, new_val)))
            _auto_record_insert_key(strip, property_name)

def _perform_color_from_plus_minus(direction, property_name, min_val, max_val):
    sensitivity = config.PLUS_MINUS_SENSITIVITY_COLOR
    if state.control_state['shift_active']:
        sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = direction * sensitivity
    _perform_color_continuous(delta, property_name, min_val, max_val)

def _perform_color_from_jog(jog_value, tool_name, property_name, min_val, max_val):
    sensitivity = config.JOG_SENSITIVITY_COLOR
    if state.control_state['shift_active']:
        sensitivity /= config.PRECISION_MODE_DIVISOR
    delta = jog_value * sensitivity
    _perform_color_with_snap(delta, tool_name, property_name, min_val, max_val)

def _handle_color_keyframe(address, args, property_name):
    if not args or not args[0]: return
    strips, frame = _get_color_compatible_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        strip.keyframe_insert(data_path=property_name, frame=frame)
    _tag_vse_redraw()

def _handle_color_delete(address, args, property_name):
    if not args or not args[0]: return
    strips, frame = _get_color_compatible_strips(), bpy.context.scene.frame_current
    if not strips: return
    for strip in strips:
        try:
            strip.keyframe_delete(data_path=property_name, frame=frame)
        except RuntimeError: pass
    _tag_vse_redraw()

def handle_use_snap_limit_toggle(address, args):
    if not args or not isinstance(args[0], bool): return
    state.control_state['use_snap_limit'] = args[0]
    is_active = state.control_state['use_snap_limit']
    print(f"OSC VSE: El límite/snap de herramientas ha sido {'ACTIVADO' if is_active else 'DESACTIVADO'}.")
    osc_feedback.send("/use_limit/state", 1 if is_active else 0)

def handle_tool_activation(address, args):
    if not args:
        return

    try:
        is_pressed = bool(args[0])
    except (ValueError, TypeError):
        return

    tool_name = address.strip('/')

    if is_pressed:
        if tool_name in ['saturation', 'multiply'] and not _get_color_compatible_strips():
            print(f"OSC Info: No hay strips compatibles seleccionados para la herramienta '{tool_name}'.")
            return
        if tool_name == 'blend' and not _get_blend_compatible_strips():
             print("OSC Info: No strips that support blend keyframing are selected.")
             return
        if tool_name.startswith('crop_') and not _get_selected_crop_strips():
            print("OSC Info: No strips that support cropping are selected.")
            return

    if is_pressed:
        bpy.ops.ed.undo_push(message=f"OSC Tool: {tool_name}")
        if tool_name not in state.control_state['active_tools']:
            state.control_state['active_tools'].add(tool_name)

            if tool_name in ['off_start', 'off_end']:
                state.control_state['offset_frame_accumulator'] = 0.0

                # --- SNAP INICIAL AL PRESIONAR LA HERRAMIENTA ---
                if state.control_state.get('strip_nav_follow_active', False):
                    active_strip = bpy.context.scene.sequence_editor.active_strip
                    if active_strip:
                        target_frame = 0
                        # --- INICIO DE FÓRMULA CORREGIDA ---
                        if tool_name == 'off_end':
                            # Fórmula correcta para el final
                            target_frame = active_strip.frame_final_start + active_strip.frame_final_duration - 1
                        else: # off_start
                            # Fórmula directa para el inicio
                            target_frame = active_strip.frame_final_start
                        # --- FIN DE FÓRMULA CORREGIDA ---

                        bpy.context.scene.frame_current = int(round(target_frame))

            tools_sin_reset = ['alpha', 'blend']
            if tool_name not in tools_sin_reset:
                reset_all_snap_states()
    else:
        state.control_state['active_tools'].discard(tool_name)

def handle_autokey_toggle(address, args):
    if not args:
        current_state = bpy.context.tool_settings.use_keyframe_insert_auto
        bpy.context.tool_settings.use_keyframe_insert_auto = not current_state
    else:
        bpy.context.tool_settings.use_keyframe_insert_auto = bool(args[0])
    new_state = bpy.context.tool_settings.use_keyframe_insert_auto

    # Sincroniza nuestro estado interno para "auto record" con el mensaje de Auto Key
    state.control_state['auto_record'] = bool(new_state)

    osc_feedback.send("/key_auto/state", 1 if new_state else 0)
    print(f"Blender Auto-Keyframing: {'ACTIVADO' if new_state else 'DESACTIVADO'}")

def register_actions():
    state.plus_minus_actions['zoom'] = _perform_zoom_from_plus_minus
    state.jog_actions['zoom'] = _perform_zoom_from_jog
    state.tool_specific_actions['zoom'] = { '/key': _handle_zoom_keyframe, '/del': _handle_zoom_delete }
    state.plus_minus_actions['posx'] = _perform_position_x_from_plus_minus
    state.jog_actions['posx'] = _perform_position_x_from_jog
    state.tool_specific_actions['posx'] = { '/key': lambda a, r: _handle_position_keyframe(a, r, 'x'), '/del': lambda a, r: _handle_position_delete(a, r, 'x') }
    state.plus_minus_actions['posy'] = _perform_position_y_from_plus_minus
    state.jog_actions['posy'] = _perform_position_y_from_jog
    state.tool_specific_actions['posy'] = { '/key': lambda a, r: _handle_position_keyframe(a, r, 'y'), '/del': lambda a, r: _handle_position_delete(a, r, 'y') }
    state.plus_minus_actions['rot'] = _perform_rotation_from_plus_minus
    state.jog_actions['rot'] = _perform_rotation_from_jog
    state.tool_specific_actions['rot'] = { '/key': _handle_rotation_keyframe, '/del': _handle_rotation_delete }
    state.plus_minus_actions['origx'] = lambda d: _perform_origin_from_plus_minus(d, 0)
    state.jog_actions['origx'] = lambda v: _perform_origin_from_jog(v, 0)
    state.tool_specific_actions['origx'] = { '/key': _handle_origin_keyframe, '/del': _handle_origin_delete }
    state.plus_minus_actions['origy'] = lambda d: _perform_origin_from_plus_minus(d, 1)
    state.jog_actions['origy'] = lambda v: _perform_origin_from_jog(v, 1)
    state.tool_specific_actions['origy'] = { '/key': _handle_origin_keyframe, '/del': _handle_origin_delete }
    state.plus_minus_actions['alpha'] = _perform_alpha_from_plus_minus
    state.jog_actions['alpha'] = _perform_alpha_from_jog
    state.tool_specific_actions['alpha'] = { '/key': _handle_alpha_keyframe, '/del': _handle_alpha_delete }
    state.tool_specific_actions['blend'] = { '/key': _handle_blend_keyframe, '/del': _handle_blend_delete }

    crop_tools = { 'crop_l': 'left', 'crop_r': 'right', 'crop_t': 'top', 'crop_b': 'bottom' }
    for tool_name, crop_side in crop_tools.items():
        state.plus_minus_actions[tool_name] = (lambda d, side=crop_side: _perform_crop_from_plus_minus(d, side))
        state.jog_actions[tool_name] = (lambda v, side=crop_side: _perform_crop_from_jog(v, side))
        state.tool_specific_actions[tool_name] = {
            '/key': (lambda a, r, side=crop_side: _handle_crop_keyframe(a, r, side)),
            '/del': (lambda a, r, side=crop_side: _handle_crop_delete(a, r, side)),
        }

    toggle_tools = {
        'mirror_x': 'use_flip_x',
        'mirror_y': 'use_flip_y',
        'reverse': 'use_reverse_frames',
    }
    for tool_name, prop_name in toggle_tools.items():
        state.plus_minus_actions[tool_name] = (lambda d, t=tool_name: _perform_toggle_from_plus_minus(t))
        state.jog_actions[tool_name] = (lambda v, t=tool_name: _perform_toggle_from_jog(v, t))
        state.tool_specific_actions[tool_name] = {
            '/key': (lambda a, r, p=prop_name: _handle_boolean_keyframe(a, r, p)),
            '/del': (lambda a, r, p=prop_name: _handle_boolean_delete(a, r, p)),
        }

    state.plus_minus_actions['saturation'] = lambda d: _perform_color_from_plus_minus(d, 'color_saturation', 0.0, 2.0)
    state.jog_actions['saturation'] = lambda v: _perform_color_from_jog(v, 'saturation', 'color_saturation', 0.0, 2.0)
    state.tool_specific_actions['saturation'] = {
        '/key': lambda a, r: _handle_color_keyframe(a, r, 'color_saturation'),
        '/del': lambda a, r: _handle_color_delete(a, r, 'color_saturation'),
    }

    state.plus_minus_actions['multiply'] = lambda d: _perform_color_from_plus_minus(d, 'color_multiply', 0.0, 20.0)
    state.jog_actions['multiply'] = lambda v: _perform_color_from_jog(v, 'multiply', 'color_multiply', 0.0, 20.0)
    state.tool_specific_actions['multiply'] = {
        '/key': lambda a, r: _handle_color_keyframe(a, r, 'color_multiply'),
        '/del': lambda a, r: _handle_color_delete(a, r, 'color_multiply'),
    }

def register(): pass
def unregister(): pass