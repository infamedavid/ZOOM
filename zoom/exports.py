# exports.py

import bpy
import os
from . import state
from . import osc_feedback

# =====================================================================
# == DICCIONARIO CENTRAL DE PRESETS DE EXPORTACIÓN
# =====================================================================
PRESETS = {
    # --- Profesional y Archivo ---
    'master_imagenes_exr': {
        'display_name': 'MSTR_EXR',
        'image_settings.file_format': 'OPEN_EXR', 'image_settings.color_mode': 'RGBA',
        'image_settings.color_depth': '16', 'image_settings.exr_codec': 'ZIP', 'use_audio': False,
    },
    'master_video_ffv1': {
        'display_name': 'MSTR_FFV1',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MATROSKA',
        'ffmpeg.codec': 'FFV1', 'use_audio': True, 'ffmpeg.audio_codec': 'FLAC',
    },

    # --- YouTube ---
    'youtube_1080p_sdr': {
        'display_name': 'YT_1080',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4', 'ffmpeg.codec': 'H264',
        'ffmpeg.constant_rate_factor': 'HIGH', 'ffmpeg.ffmpeg_preset': 'SLOW', 'resolution_x': 1920, 'resolution_y': 1080,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 320,
    },
    'youtube_4k_hdr': {
        'display_name': 'YT_4K_HDR',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4', 'ffmpeg.codec': 'H265',
        'ffmpeg.constant_rate_factor': 'HIGH', 'ffmpeg.ffmpeg_preset': 'SLOW', 'resolution_x': 3840, 'resolution_y': 2160,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 320,
    },
    'youtube_shorts': {
    'display_name': 'YT_SHORTS',
    '__based_on__': 'youtube_1080p_sdr', # Use the same quality/audio settings
    'resolution_x': 1080,
    'resolution_y': 1920,
    },

    # --- Vimeo ---
    'vimeo_1080p_hq': {
        'display_name': 'VIMEO_HQ',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4', 'ffmpeg.codec': 'H264',
        'ffmpeg.constant_rate_factor': 'HIGH', 'ffmpeg.ffmpeg_preset': 'SLOW', 'use_audio': True,
        'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 320,
    },
    
    # --- Instagram ---
    'instagram_feed_square': {
        'display_name': 'IG_SQR',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4', 'ffmpeg.codec': 'H264',
        'ffmpeg.constant_rate_factor': 'MEDIUM', 'resolution_x': 1080, 'resolution_y': 1080,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 128,
    },
    'instagram_feed_portrait': {
        'display_name': 'IG_VRT',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4', 'ffmpeg.codec': 'H264',
        'ffmpeg.constant_rate_factor': 'MEDIUM', 'resolution_x': 1080, 'resolution_y': 1350,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 128,
    },
    'instagram_reels_stories': {
        'display_name': 'IG_REELS',
        'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4', 'ffmpeg.codec': 'H264',
        'ffmpeg.constant_rate_factor': 'MEDIUM', 'resolution_x': 1080, 'resolution_y': 1920,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 128,
    },

    # --- Otras Plataformas ---
    'facebook_1080p_hq': { 'display_name': 'FB_1080', '__based_on__': 'youtube_1080p_sdr' },
    'tiktok_1080p': {
        'display_name': 'TIKTOK', 'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4',
        'ffmpeg.codec': 'H265', 'ffmpeg.constant_rate_factor': 'MEDIUM', 'resolution_x': 1080, 'resolution_y': 1920,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 192,
    },
    'twitter_720p': {
        'display_name': 'X_720', 'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'MPEG4',
        'ffmpeg.codec': 'H264', 'ffmpeg.constant_rate_factor': 'MEDIUM', 'resolution_x': 1280, 'resolution_y': 720,
        'use_audio': True, 'ffmpeg.audio_codec': 'AAC', 'ffmpeg.audio_bitrate': 128,
    },

    # --- Plataformas Abiertas ---
    'peertube_1080p_vp9': {
        'display_name': 'PEERTUBE', 'image_settings.file_format': 'WEBM', 'ffmpeg.codec': 'VP9',
        'ffmpeg.constant_rate_factor': 'MEDIUM', 'resolution_x': 1920, 'resolution_y': 1080,
        'use_audio': True, 'ffmpeg.audio_codec': 'OPUS',
    },
    'odysee_lbry_1080p': { 'display_name': 'ODYSEE', '__based_on__': 'youtube_1080p_sdr' },
    
    # --- Solo Audio ---
    'audio_master_wav': {
        'display_name': 'AUD_WAV', 'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'WAV',
        'use_audio': True, 'ffmpeg.audio_codec': 'PCM',
    },
    'audio_lossless_flac': {
        'display_name': 'AUD_FLAC', 'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'FLAC',
        'use_audio': True, 'ffmpeg.audio_codec': 'FLAC',
    },
    'audio_compressed_opus': {
        'display_name': 'AUD_OPUS', 'image_settings.file_format': 'FFMPEG', 'ffmpeg.format': 'OGG',
        'use_audio': True, 'ffmpeg.audio_codec': 'OPUS',
    },
}

def _clear_export_feedback_timer():
    """Limpia el feedback de exportación y resetea el temporizador en el estado."""
    osc_feedback.send("/export/feedback/name", "       ")
    osc_feedback.send_active_tool_value_feedback(" ")
    state.control_state['export_feedback_timer'] = None
    return None # Detiene el temporizador

def _send_export_feedback():
    """
    Envía el feedback compacto y gestiona un temporizador de 5 segundos para limpiarlo.
    """
    # 1. Cancela cualquier temporizador de limpieza anterior que esté activo
    timer = state.control_state.get('export_feedback_timer')
    if timer and bpy.app.timers.is_registered(timer):
        bpy.app.timers.unregister(timer)

    # 2. Envía el feedback actual a la superficie
    render_settings = bpy.context.scene.render
    preset_info = state.control_state.get('last_export_preset', {'display_name': 'MANUAL'})
    display_name = preset_info['display_name']
    scale_percentage = render_settings.resolution_percentage
    
    osc_feedback.send("/export/feedback/name", display_name)
    osc_feedback.send_active_tool_value_feedback(f"{scale_percentage}%")

    # 3. Inicia un nuevo temporizador de 5 segundos para limpiar el feedback
    new_timer = bpy.app.timers.register(_clear_export_feedback_timer, first_interval=5.0)
    state.control_state['export_feedback_timer'] = new_timer


def apply_preset(preset_name: str):
    """Aplica un preset de renderizado y envía feedback."""
    if preset_name not in PRESETS:
        print(f"OSC Exports: Preset '{preset_name}' no encontrado.")
        return

    bpy.ops.ed.undo_push(message=f"OSC Apply Preset: {preset_name}")
    
    preset_data = PRESETS[preset_name]
    render_settings = bpy.context.scene.render
    
    if '__based_on__' in preset_data:
        base_preset = PRESETS.get(preset_data['__based_on__'], {})
        final_settings = {**base_preset, **preset_data}
    else:
        final_settings = preset_data

    for key, value in final_settings.items():
        if key in ['display_name', '__based_on__']: continue
        try:
            obj, prop = render_settings, key
            if '.' in key:
                parts = key.split('.')
                obj = getattr(render_settings, parts[0])
                prop = parts[1]
            setattr(obj, prop, value)
        except (AttributeError, TypeError) as e:
            print(f"WARN: No se pudo aplicar '{key}': {e}")
            
    state.control_state['last_export_preset'] = PRESETS[preset_name]
    _send_export_feedback()
    osc_feedback.send_action_feedback(PRESETS[preset_name]['display_name'])

def set_scale(percentage: int):
    """Ajusta la escala de resolución y envía feedback."""
    if not (0 < percentage <= 200): return
    bpy.context.scene.render.resolution_percentage = percentage
    _send_export_feedback()

def handle_render(address, args):
    """Inicia el render de la animación."""
    if not args or not args[0]: return
    osc_feedback.send_action_feedback("RENDERING")
    bpy.ops.render.render('INVOKE_DEFAULT', animation=True)

# --- Handlers OSC ---
def handle_apply_preset(address, args):
    if not args or not args[0]: return
    try: apply_preset(address.split('/')[-1])
    except IndexError: print(f"Dirección de preset inválida: {address}")

def handle_set_scale(address, args):
    if not args or not args[0]: return
    try: set_scale(int(address.split('/')[-1]))
    except (IndexError, ValueError): print(f"Dirección de escala inválida: {address}")


def handle_play_render(address, args):
    """
    Intenta reproducir la última animación renderizada.
    Delega el manejo de errores al operador nativo de Blender.
    """
    if not args or not args[0]:
        return

    try:
        bpy.ops.render.play_rendered_anim('INVOKE_DEFAULT')
    except Exception as e:
        # El operador puede fallar si no hay render; el error se mostrará
        # en la Consola de Información de Blender.
        print(f"OSC Play Render: El operador falló. Probablemente no hay un render válido. Error: {e}")


def register():
    if 'last_export_preset' not in state.control_state:
        state.control_state['last_export_preset'] = {'display_name': 'N/A'}

def unregister():
    pass