"""Shared pytest setup (§13).

Tier A tests need nothing beyond `crash_forge` being importable — `core/`
has zero bpy imports (§3 rule 3), and neither does the package `__init__`
at module level, so plain sys.path setup is enough to prove both are pure:
if either quietly grew a bpy dependency, `from crash_forge.core import x`
would fail outright in this Blender-less sandbox.

Tier B tests additionally need the `stubbed_bpy` fixture to make `import
bpy`/`bmesh`/`mathutils` resolve to tests/stubs/.
"""
import importlib
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
STUBS_DIR = TESTS_DIR / "stubs"
REPO_ROOT = TESTS_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _purge(prefixes):
    for name in list(sys.modules):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            del sys.modules[name]


@pytest.fixture
def stubbed_bpy():
    sys.path.insert(0, str(STUBS_DIR))
    _purge(("bpy", "bmesh", "mathutils", "crash_forge"))
    try:
        yield importlib.import_module("crash_forge")
    finally:
        _purge(("bpy", "bmesh", "mathutils", "crash_forge"))
        sys.path.remove(str(STUBS_DIR))
