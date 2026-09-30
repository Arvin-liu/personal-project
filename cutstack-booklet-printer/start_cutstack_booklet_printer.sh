#!/usr/bin/env bash
# macOS launcher for CutStack Booklet Printer.
# Build the app bundle on first use, then hand it to LaunchServices so the
# bundle launcher runs with the same parent-process checks as project 14.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="CutStackBookletPrinter"
APP_DIR="$ROOT_DIR/$APP_NAME.app"
BUILD_SCRIPT="$ROOT_DIR/build_cutstack_app.sh"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This launcher is for macOS only." >&2
  exit 1
fi

if [[ ! -x "$APP_DIR/Contents/MacOS/$APP_NAME" ]]; then
  "$BUILD_SCRIPT"
fi

open "$APP_DIR"
