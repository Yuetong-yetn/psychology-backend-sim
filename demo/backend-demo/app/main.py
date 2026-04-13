from __future__ import annotations

import importlib
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = CURRENT_DIR.parents[2]

backend_root_str = str(BACKEND_ROOT)
if backend_root_str not in sys.path:
    sys.path.insert(0, backend_root_str)


def _load_app():
    for module_name in ("webapp",):
        try:
            module = importlib.import_module(module_name)
            return module.app
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError(
        "Could not import the real FastAPI app. Expected `webapp.py` in the backend root "
        "above `demo/backend-demo`."
    )


app = _load_app()
