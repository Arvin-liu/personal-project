#!/usr/bin/env bash
# Build + install CutStack Booklet Printer as a macOS .app into /Applications.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_SCRIPT="$ROOT_DIR/build_cutstack_app.sh"
APP_NAME="CutStackBookletPrinter"
SOURCE_APP="$ROOT_DIR/$APP_NAME.app"
PRIMARY_DEST="/Applications"
FALLBACK_DEST="$HOME/Applications"

"$BUILD_SCRIPT"

DEST_DIR="$PRIMARY_DEST"
if [[ ! -w "$PRIMARY_DEST" ]]; then
  mkdir -p "$FALLBACK_DEST"
  DEST_DIR="$FALLBACK_DEST"
fi

DEST_APP="$DEST_DIR/$APP_NAME.app"
# Kill any running instance so the freshly built app can start (single-instance lock).
pkill -f "$APP_NAME.app/Contents/Resources/main.py" 2>/dev/null || true
sleep 1
rm -rf "$DEST_APP"
cp -R "$SOURCE_APP" "$DEST_DIR/"
open "$DEST_APP" >/dev/null 2>&1 || true

echo "Installed to: $DEST_APP"
