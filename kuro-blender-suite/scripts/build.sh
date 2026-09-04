#!/usr/bin/env bash
# Assembles an installable, self-contained .zip per add-on: vendors
# kuro_core into <addon>/kuro_core/ and rewrites the dev-time top-level
# `from kuro_core import ...` imports to relative `from .kuro_core import
# ...` (see BLENDER_ADDON_MASTER_PLAN.md §1 "Vendoring rule"). Studios
# install one zip, not three plus a shared dependency.
#
# Usage: scripts/build.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$REPO_ROOT/build"
DIST_DIR="$REPO_ROOT/dist"

# Only add-ons that actually exist yet (MatForge/RuinFX come later per the
# phase plan) are built; add names here as they're scaffolded.
ADDONS=(stormkit)

rm -rf "$BUILD_DIR" "$DIST_DIR"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

for addon in "${ADDONS[@]}"; do
  echo "Building ${addon}..."
  src="$REPO_ROOT/$addon"
  out="$BUILD_DIR/$addon"
  mkdir -p "$out"

  cp -r "$src/." "$out/"
  cp -r "$REPO_ROOT/kuro_core" "$out/kuro_core"
  find "$out" -name '__pycache__' -type d -exec rm -rf {} +

  find "$out" -name '*.py' -print0 | xargs -0 sed -i \
    -e 's/^from kuro_core import/from .kuro_core import/' \
    -e 's/^from kuro_core\./from .kuro_core./' \
    -e 's/^import kuro_core$/from . import kuro_core/'

  version="$(python3 -c "
import tomllib
with open('$src/blender_manifest.toml', 'rb') as f:
    print(tomllib.load(f)['version'])
" 2>/dev/null || echo "0.0.0")"

  zip_path="$DIST_DIR/${addon}-${version}.zip"
  (cd "$BUILD_DIR" && zip -rq "$zip_path" "$addon" -x '*/__pycache__/*')
  echo "  -> ${zip_path}"
done

echo "Done."
