"""Frozen-app / double-click launcher for GoldApp Desktop.

Running ``python_gui/main.py`` directly fails because the module uses package
relative imports (``from .core ...``). This launcher puts the repo root on
``sys.path`` and starts the app through the package, so it works both as:

    python python_gui/launch.py        (dev)
    GoldApp.exe                        (PyInstaller one-folder build entry)
"""

from __future__ import annotations

import os
import sys

# repo root = parent of the python_gui package directory
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from python_gui.main import main  # noqa: E402

if __name__ == "__main__":
    main()
