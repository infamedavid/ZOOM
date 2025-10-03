# channels.py
"""
Gestión de propiedades de canal para OSC VSE.
Implementa el control de mute y lock a nivel de canal, afectando
la salida del canal completo de forma no destructiva.
"""

import bpy
from . import osc_feedback

def _handle_channel_toggle(address, args, prop_name):
    """
    Función genérica para alternar una propiedad booleana (mute/lock)
    de un canal completo en el VSE.
    """
    # Ejecutar solo al presionar el botón
    if not args or not args[0]:
        return

    # 1. Obtener el contexto del secuenciador
    sequencer = bpy.context.scene.sequence_editor
    if not sequencer:
        print("OSC Channels: No se encontró un editor de secuencias.")
        return

    # 2. Parsear el índice del canal desde la dirección OSC
    try:
        channel_index = int(address.split('/')[-1])
        if channel_index <= 0:
            print(f"OSC Channels: Índice de canal inválido: {channel_index}")
            return
    except (ValueError, IndexError):
        print(f"OSC Channels: Dirección inválida, no se pudo parsear el número de canal: {address}")
        return

    # 3. Construir el nombre del canal y alternar la propiedad
    channel_name = f"Channel {channel_index}"
    try:
        channel = sequencer.channels[channel_name]
        
        action_str = "Mute" if prop_name == "mute" else "Lock"
        bpy.ops.ed.undo_push(message=f"OSC Toggle Channel {action_str}")

        current_state = getattr(channel, prop_name)
        new_state = not current_state
        setattr(channel, prop_name, new_state)

        # Imprimir feedback a la consola
        state_str = "ON" if new_state else "OFF"
        print(f"OSC Channels: Canal {channel_index} -> {action_str.upper()} {state_str}")
        
        # (Opcional) Enviar feedback a la superficie
        # osc_feedback.send(f"/channel/{channel_index}/{prop_name}", 1 if new_state else 0)

    except KeyError:
        print(f"OSC Channels: El canal '{channel_name}' no existe en el secuenciador.")
    except Exception as e:
        print(f"OSC Channels: Error al modificar la propiedad '{prop_name}' del canal {channel_index}: {e}")

# --- Manejadores OSC Públicos ---

def handle_channel_lock(address, args):
    """Manejador para /channel_lock/N"""
    _handle_channel_toggle(address, args, 'lock')

def handle_channel_mute(address, args):
    """Manejador para /channel_mute/N"""
    _handle_channel_toggle(address, args, 'mute')

def register():
    """Función de registro (opcional para este módulo)."""
    pass

def unregister():
    """Función de anulación de registro (opcional para este módulo)."""
    pass