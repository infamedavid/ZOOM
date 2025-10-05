# preset_0.py

preset_info = {
    "name": "Sample",
    "author": "Infame",
    "version": (1, 0, 0),
    "blender": (4, 1, 0),
    "zoom": (1,0,0),
    "description": "SAMPLE PRESET, SEND A RESPONSE VIA OSC ."

from .. import osc_feedback, state, macros

def run(context, *args, **kwargs):
    """
    Preset 00 - ejemplo simple
    """
    N = 0
    try:
        if state.control_state.get("shift_active", False):
            osc_feedback.send("/msg", "preset_00: shift ON - no implementado")
        else:
            osc_feedback.send("/msg", "preset_00: ejecutado (ejemplo)")
        # ejemplo de persistencia: cuenta cuántas veces se ejecutó
        data = macros.load_preset_data(N, default={"count": 0})
        data["count"] = data.get("count", 0) + 1
        macros.save_preset_data(N, data)
    except Exception as e:
        osc_feedback.send("/msg", f"preset_00 error: {e}")

    # feedback obligatorio
    osc_feedback.send(f"/PRST_{N}", 0)