#!/usr/bin/env bash
# Runs the full KURO suite headlessly. Exits nonzero on any test failure.
# Usage: scripts/test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

if ! command -v blender >/dev/null 2>&1; then
  echo "ERROR: 'blender' not found on PATH." >&2
  echo "Install Blender 5.1.2 (primary target) or 4.5 LTS and try again." >&2
  exit 1
fi

echo "Using: $(blender --version | head -n1)"
blender --background --factory-startup --python "$REPO_ROOT/tests/run_all.py"
