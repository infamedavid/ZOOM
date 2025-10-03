# preferences.py

import bpy

class OSC_Preset(bpy.types.PropertyGroup):
    """Define un único preset de configuración de red."""
    name: bpy.props.StringProperty(name="Preset Name", default="Preset")
    server_ip: bpy.props.StringProperty(name="Server IP", default="0.0.0.0")
    server_port: bpy.props.IntProperty(name="Server Port", default=8000)
    client_ip: bpy.props.StringProperty(name="Client IP", default="127.0.0.1")
    client_port: bpy.props.IntProperty(name="Client Port", default=8001)

def update_active_preset(self, context):
    """
    Se ejecuta cuando el usuario selecciona un preset de la lista.
    Copia los valores del preset seleccionado a la configuración activa de la escena.
    """
    prefs = context.preferences.addons[__package__].preferences
    active_preset = prefs.presets[prefs.active_preset_index]
    props = context.scene.osc_vse_properties

    props.ip = active_preset.server_ip
    props.port = active_preset.server_port
    props.client_ip = active_preset.client_ip
    props.client_port = active_preset.client_port
    
    print(f"OSC Preset '{active_preset.name}' loaded.")

class OSCVSEAddonPreferences(bpy.types.AddonPreferences):
    """Clase principal para las preferencias del addon."""
    bl_idname = __package__

    presets: bpy.props.CollectionProperty(type=OSC_Preset, name="Network Presets")
    active_preset_index: bpy.props.IntProperty(
        name="Active Preset", 
        default=0,
        update=update_active_preset
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Aquí se guardarán las preferencias globales del addon OSC VSE.")
        # Podríamos añadir más preferencias globales aquí en el futuro.

classes = (
    OSC_Preset,
    OSCVSEAddonPreferences,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)