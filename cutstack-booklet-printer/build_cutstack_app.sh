#!/usr/bin/env bash
# Build CutStack Booklet Printer as a self-contained macOS .app.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="CutStackBookletPrinter"
DISPLAY_NAME="CutStack 小册子打印机"
APP_DIR="$ROOT_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RES_DIR="$CONTENTS_DIR/Resources"
LAUNCHER="$MACOS_DIR/$APP_NAME"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
ICON_SRC="$ROOT_DIR/assets/app-icon.svg"
ICONSET_DIR="$APP_DIR/icon.iconset"
ICON_ICNS="$CONTENTS_DIR/Resources/$APP_NAME.icns"
LAUNCH_TOKEN="$(python3 - <<'PY'
import uuid
print(uuid.uuid4().hex)
PY
)"
TOKEN_FILE="$ROOT_DIR/launch_token.txt"
MACOS_TOKEN_FILE="$MACOS_DIR/launch_token.txt"
RES_TOKEN_FILE="$RES_DIR/launch_token.txt"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$RES_DIR"
printf '%s\n' "$LAUNCH_TOKEN" > "$TOKEN_FILE"
printf '%s\n' "$LAUNCH_TOKEN" > "$MACOS_TOKEN_FILE"
printf '%s\n' "$LAUNCH_TOKEN" > "$RES_TOKEN_FILE"

# App source modules (third-party deps live in the .venv and resolve automatically).
cp "$ROOT_DIR"/main.py "$RES_DIR"/
cp "$ROOT_DIR"/ui.py "$RES_DIR"/
cp "$ROOT_DIR"/printer.py "$RES_DIR"/
cp "$ROOT_DIR"/impose.py "$RES_DIR"/
cp "$ROOT_DIR"/editor_document.py "$RES_DIR"/
cp "$ROOT_DIR"/README.md "$RES_DIR"/ 2>/dev/null || true
cp "$ROOT_DIR"/launcher_guard.sh "$RES_DIR"/
mkdir -p "$RES_DIR/assets"
cp "$ROOT_DIR"/assets/floating-menu.png "$RES_DIR/assets/"
cp "$ICON_SRC" "$RES_DIR/$APP_NAME.svg"

# Icon
rm -rf "$ICONSET_DIR"
mkdir -p "$ICONSET_DIR"
BASE_ICON_PNG="$APP_DIR/icon-base.png"
sips -s format png "$ICON_SRC" --out "$BASE_ICON_PNG" >/dev/null
for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$BASE_ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
  sips -z $((size * 2)) $((size * 2)) "$BASE_ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done
cp "$BASE_ICON_PNG" "$RES_DIR/$APP_NAME.png"
iconutil -c icns "$ICONSET_DIR" -o "$ICON_ICNS" >/dev/null
rm -rf "$ICONSET_DIR"
rm -f "$BASE_ICON_PNG"

cat > "$CONTENTS_DIR/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${DISPLAY_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${DISPLAY_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>io.github.arvin-liu.cutstackbookletprinter</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>${APP_NAME}.icns</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleSignature</key>
  <string>CSBP</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
</dict>
</plist>
PLIST

cat > "$CONTENTS_DIR/PkgInfo" <<'PKG'
APPLCSBP
PKG

cat > "$LAUNCHER" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail

APP_CONTENTS="\$(cd "\$(dirname "\$0")/.." && pwd)"
APP_RESOURCES="\$APP_CONTENTS/Resources"
VENV_PYTHON="$VENV_PYTHON"
PYTHON_BIN=""

source "\$APP_RESOURCES/launcher_guard.sh"
pd_require_allowed_parent
pd_init_launch_token
cd "\$APP_RESOURCES"
PYTHON_BIN=\$(pd_find_python 'import ui' \\
  "\$(printenv CUTSTACK_PYTHON || true)" \\
  "\$VENV_PYTHON" \\
  "\$(command -v python3 || true)" \\
  "/opt/homebrew/bin/python3" \\
  "/usr/local/bin/python3" \\
  "/usr/bin/python3") || PYTHON_BIN=""

if [[ -z "\$PYTHON_BIN" ]]; then
  osascript -e 'display alert "CutStack 小册子打印机" message "没有找到包含应用依赖的可用 Python 环境。请检查项目 .venv 或设置 CUTSTACK_PYTHON。"' >/dev/null 2>&1 || true
  exit 1
fi

export TK_SILENCE_DEPRECATION=1
exec "\$PYTHON_BIN" "\$APP_RESOURCES/main.py" "\$@"
LAUNCHER

chmod +x "$LAUNCHER"

echo "Built: $APP_DIR"
