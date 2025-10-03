# macros.py
import importlib
import os
import sys
import traceback
import json
from functools import partial

import bpy

from . import osc_feedback, state

# carpeta relativa dentro del addon
PRESETS_REL_PATH = os.path.join(os.path.dirname(__file__), "presets")
# cache de módulos {N: module}
_loaded_presets = {}

def _is_preset_filename(name):
    return name.startswith("preset_") and name.endswith(".py")

def discover_presets():
    """
    Escanea zoom/presets/ y carga (importlib) todos los preset_*.py
    Indexa por N (int) proveniente de preset_NN.py
    """
    global _loaded_presets
    _loaded_presets.clear()
    if not os.path.isdir(PRESETS_REL_PATH):
        print(f"[macros] No existe la carpeta de presets: {PRESETS_REL_PATH}")
        return

    # Añadir ruta para que los imports relativos funcionen (si hace falta)
    if PRESETS_REL_PATH not in sys.path:
        sys.path.append(PRESETS_REL_PATH)

    for fn in sorted(os.listdir(PRESETS_REL_PATH)):
        if not _is_preset_filename(fn):
            continue
        name_no_ext = fn[:-3]  # preset_01
        try:
            # extraer número
            parts = name_no_ext.split("_")
            num = int(parts[-1])
        except Exception:
            print(f"[macros] Nombre de preset inválido (debe terminar en _N): {fn}")
            continue

        mod_name = f"zoom.presets.{name_no_ext}"
        try:
            if mod_name in sys.modules:
                module = importlib.reload(sys.modules[mod_name])
            else:
                module = importlib.import_module(mod_name)
            _loaded_presets[num] = module
            print(f"[macros] Preset cargado: {fn} -> macro {num}")
        except Exception as e:
            print(f"[macros] Error cargando preset {fn}: {e}")
            traceback.print_exc()

def get_presets_index():
    """Devuelve lista de números cargados (ordenados)."""
    return sorted(_loaded_presets.keys())

def _send_prst_safe(n):
    try:
        osc_feedback.send(f"/PRST_{n}", 1)
    except Exception as e:
        print(f"[macros] Error enviando /PRST_{n}: {e}")

def _run_module(module, n, context, *args, **kwargs):
    """
    Ejecuta module.run en hilo principal. Se encarga de enviar /PRST_N
    incluso si la macro falla.
    """
    try:
        if hasattr(module, "run"):
            module.run(context, *args, **(kwargs or {}))
        else:
            osc_feedback.send("/msg", f"Preset {n} no tiene run(context, ...)")
    except Exception as e:
        print(f"[macros] Error ejecutando preset {n}: {e}")
        traceback.print_exc()
        try:
            osc_feedback.send("/msg", f"Error en preset {n}: {str(e)}")
        except Exception:
            pass
    finally:
        # feedback obligatorio
        _send_prst_safe(n)

def run_macro(n, context=None, *args, **kwargs):
    """
    Invocado desde osc_server cuando llega /macro/N
    Asegura ejecución en main thread usando bpy.app.timers.register
    """
    module = _loaded_presets.get(n)
    if not module:
        print(f"[macros] Macro {n} no encontrada.")
        osc_feedback.send("/msg", f"Macro {n} no encontrada")
        # enviar PRST_N aunque no exista? mejor enviar para evitar desync en superficie:
        _send_prst_safe(n)
        return

    # programar ejecución en hilo principal
    def _runner():
        _run_module(module, n, context, *args, **(kwargs or {}))
        return None  # unregister timer (una sola llamada)
    try:
        bpy.app.timers.register(_runner)
    except Exception as e:
        print(f"[macros] No se pudo registrar timer para macro {n}: {e}")
        # fallback: intentar ejecutar directo (riesgoso si no estamos en main thread)
        _run_module(module, n, context, *args, **(kwargs or {}))

# --- Helpers para persistencia si el macro quiere usar JSON ---
def preset_data_path(n):
    """
    Devuelve la ruta absoluta donde el macro N puede guardar su JSON.
    Ej: zoom/presets/data/preset_01.json
    """
    data_dir = os.path.join(PRESETS_REL_PATH, "data")
    os.makedirs(data_dir, exist_ok=True)
    filename = f"preset_{str(n).zfill(2)}.json"
    return os.path.join(data_dir, filename)

def load_preset_data(n, default=None):
    path = preset_data_path(n)
    if not os.path.isfile(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[macros] Error leyendo JSON de preset {n}: {e}")
        return default

def save_preset_data(n, data):
    path = preset_data_path(n)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[macros] Error guardando JSON de preset {n}: {e}")
        return False
