"""Import `dyness_battery.local` without Home Assistant.

The integration's `__init__.py` imports Home Assistant, and its folder holds
`select.py` / `time.py`, which would shadow the standard library if put on
sys.path. A stub parent package exposes only the pure `local` modules.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "dyness_battery"

if "dyness_battery" not in sys.modules:
    stub = types.ModuleType("dyness_battery")
    stub.__path__ = [str(PACKAGE_DIR)]  # type: ignore[attr-defined]
    sys.modules["dyness_battery"] = stub

try:
    import pytest_homeassistant_custom_component  # noqa: F401
except ImportError:
    collect_ignore = ["ha"]
