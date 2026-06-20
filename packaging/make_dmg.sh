#!/usr/bin/env bash
#
# Build a drag-to-install Musorg-<version>.dmg from a freshly built dist/Musorg.app.
#
# The installer window shows two large icons side by side — Musorg.app on the
# left and an Applications symlink on the right — so the user just drags one
# onto the other. Layout is written headlessly by dmgbuild (no Finder
# scripting), so it works in CI and over SSH.
#
# Requires: dmgbuild  (pip install dmgbuild)
#
# Usage: packaging/make_dmg.sh
# Run from the repo root, after PyInstaller has produced dist/Musorg.app.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

APP="dist/Musorg.app"
VOL_NAME="Musorg"
VERSION="$(python3 -c "import json,pathlib; print(json.loads(pathlib.Path('frontend/package.json').read_text())['version'])")"
DMG_OUT="dist/Musorg-${VERSION}.dmg"

if [[ ! -d "$APP" ]]; then
  echo "make_dmg.sh: $APP not found — build it first (pyinstaller Musorg.spec)." >&2
  exit 1
fi

if ! python3 -c "import dmgbuild" 2>/dev/null; then
  echo "make_dmg.sh: dmgbuild not installed — run: pip install dmgbuild" >&2
  exit 1
fi

echo "Building $DMG_OUT…"
rm -f "$DMG_OUT"
MUSORG_APP="$REPO_ROOT/$APP" python3 -m dmgbuild \
  -s "$REPO_ROOT/packaging/dmg_settings.py" \
  "$VOL_NAME" "$DMG_OUT"

echo "Done: $DMG_OUT"
