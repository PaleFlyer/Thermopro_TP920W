"""Import integration modules that have no Home Assistant dependency.

The real package __init__ imports Home Assistant, so a stand-in parent package
pointing at the same directory is registered instead.
"""

import importlib
from pathlib import Path
import sys
import types

_PACKAGE = "tp920_under_test"
_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "thermopro_tp920"


def load(name: str):
    if _PACKAGE not in sys.modules:
        package = types.ModuleType(_PACKAGE)
        package.__path__ = [str(_COMPONENT)]
        sys.modules[_PACKAGE] = package
    return importlib.import_module(f"{_PACKAGE}.{name}")
