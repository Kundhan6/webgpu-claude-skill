"""Standalone Stage 0 probe runner. Run this in real Blender, NOT pytest —
it does a real `import bpy` and will fail immediately outside Blender.

Usage (Windows, Blender 5.2):

    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" ^
        --background --python tests\\blender_probe_script.py

Do NOT pass --factory-startup — extensions will not load under it (§13).

Prints the full §6 Stage 0 probe report to stdout and exits 1 if any
check failed, so it can be wired into CI later without changes.
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from crash_forge.bl import probe  # noqa: E402


def main():
    result = probe.run_probe()
    print(probe.format_report(result))
    if not result.ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
