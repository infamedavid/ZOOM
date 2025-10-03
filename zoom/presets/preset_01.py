# preset_01.py

'''
un preset es una herramienta , aoutomatizacion creada con la finalidad
de anadir nuevas funcionalizades a zoom sin necesidad de modificar su core.
'''

from .. import osc_feedback, state, macros

def run(context, *args, **kwargs):
    """
    Preset 01 - ejemplo simple
    """
    N = 1
    try:
        if state.control_state.get("shift_active", False):
            osc_feedback.send("/msg", "preset_01: shift ON - no implementado")
        else:
            osc_feedback.send("/msg", "preset_01: ejecutado (ejemplo)")
        # ejemplo de persistencia: cuenta cuántas veces se ejecutó
        data = macros.load_preset_data(N, default={"count": 0})
        data["count"] = data.get("count", 0) + 1
        macros.save_preset_data(N, data)
    except Exception as e:
        osc_feedback.send("/msg", f"preset_01 error: {e}")

    # feedback obligatorio
    osc_feedback.send(f"/PRST_{N}", 1)

