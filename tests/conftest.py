"""Test bootstrap: load the dahua_vto.client module without requiring the
homeassistant package to be installed (client.py has no HA dependency, but
importing the real ``dahua_vto`` package would execute ``__init__.py``,
which does depend on homeassistant).
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "dahua_vto"

if "dahua_vto" not in sys.modules:
    _pkg = types.ModuleType("dahua_vto")
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules["dahua_vto"] = _pkg

    for _name in ("const", "client"):
        _spec = importlib.util.spec_from_file_location(
            f"dahua_vto.{_name}", _PKG_DIR / f"{_name}.py"
        )
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[f"dahua_vto.{_name}"] = _module
        _spec.loader.exec_module(_module)
