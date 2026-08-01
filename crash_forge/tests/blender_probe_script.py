"""Standalone Stage 0 probe runner. Run this in real Blender, NOT pytest —
it does a real `import bpy` and will fail immediately outside Blender.

Usage: double-click run_probe.bat (same directory), or manually:

    "C:\\path\\to\\blender.exe" ^
        --background --python tests\\blender_probe_script.py

Do NOT pass --factory-startup — extensions will not load under it (§13).

Never assumes a Blender version. §4 names 5.2 LTS as primary, but nothing
here gates on that — the version actually running is printed first and
the probe runs regardless, exactly because "probe, never assume" (§3
rule 1) applies to the host Blender build too, not just its API surface.
"""
import os
import sys

# Print the Blender version before anything else, and before it's even
# possible for an import to fail — this must survive a broken install.
try:
    import bpy
    print(f"Blender version: {bpy.app.version_string}", flush=True)
except Exception as exc:
    print(f"Blender version: <could not read bpy.app.version_string: {exc}>", flush=True)

# blender_probe_script.py lives at crash_forge/tests/blender_probe_script.py;
# `import crash_forge` needs crash_forge's *parent* directory on sys.path,
# not crash_forge itself. run_probe.bat cd's into crash_forge\ before
# invoking Blender, and Blender's --background --python does not add the
# script's parent tree to sys.path on its own, so this has to be explicit.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # crash_forge/tests
_CRASH_FORGE_DIR = os.path.dirname(_THIS_DIR)                   # crash_forge
REPO_ROOT = os.path.dirname(_CRASH_FORGE_DIR)                   # repo root
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Defensive: if Blender's extension/addon system already imported a
# `crash_forge` from somewhere else (an installed copy, possibly stale)
# before this script ran, that import is sitting in sys.modules and would
# shadow the REPO_ROOT one no matter what sys.path says — Python checks
# sys.modules before consulting sys.path at all. Drop any such entries so
# the import below is forced to come from REPO_ROOT.
for _name in list(sys.modules):
    if _name == "crash_forge" or _name.startswith("crash_forge."):
        del sys.modules[_name]

import crash_forge  # noqa: E402
from crash_forge import bl as crash_forge_bl  # noqa: E402
from crash_forge.bl import probe  # noqa: E402

print(f"crash_forge package resolved from: {crash_forge.__file__}", flush=True)
print(f"crash_forge.bl resolved from: {crash_forge_bl.__file__}", flush=True)
print(f"crash_forge.bl.probe resolved from: {probe.__file__}", flush=True)

_resolved_root = os.path.abspath(REPO_ROOT)
assert os.path.commonpath([os.path.abspath(crash_forge.__file__), _resolved_root]) == _resolved_root, (
    f"crash_forge resolved from an unexpected location ({crash_forge.__file__}), "
    f"not under {REPO_ROOT} — a stale installed copy is shadowing this repo."
)


def main():
    result = probe.run_probe()
    print(probe.format_report(result))
    if not result.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
