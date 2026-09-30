#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="英文阅读器"
DISPLAY_NAME="英文阅读器"
APP_DIR="$ROOT_DIR/$APP_NAME.app"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RES_DIR="$CONTENTS_DIR/Resources"
LAUNCHER="$MACOS_DIR/$APP_NAME"
ICON_SRC="$ROOT_DIR/assets/app-icon.svg"
ROOT_VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
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

cp "$ROOT_DIR"/app.py "$RES_DIR"/
cp "$ROOT_DIR"/hermes_fast_oneshot.py "$RES_DIR"/
cp "$ROOT_DIR"/README.md "$RES_DIR"/
cp "$ROOT_DIR"/start_ebook_reader.sh "$RES_DIR"/
cp "$ROOT_DIR"/launcher_guard.sh "$RES_DIR"/
cp "$ICON_SRC" "$RES_DIR/$APP_NAME.svg"

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
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>${DISPLAY_NAME}</string>
  <key>CFBundleDisplayName</key>
  <string>${DISPLAY_NAME}</string>
  <key>CFBundleIdentifier</key>
  <string>io.github.arvin-liu.personalenglishreader</string>
  <key>CFBundleVersion</key>
  <string>1.0.0</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0.0</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleSignature</key>
  <string>EPRD</string>
  <key>LSMinimumSystemVersion</key>
  <string>13.0</string>
</dict>
</plist>
PLIST

cat > "$CONTENTS_DIR/PkgInfo" <<'PKG'
APPLEPRD
PKG

cat > "$LAUNCHER" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail

APP_CONTENTS="\$(cd "\$(dirname "\$0")/.." && pwd)"
APP_RESOURCES="\$APP_CONTENTS/Resources"
APP_DATA_DIR="\$HOME/Library/Application Support/14_EBook_Reader_Python"
PIPER_MODEL_DIR="\$APP_DATA_DIR/piper_models"
ROOT_VENV_PYTHON="$ROOT_VENV_PYTHON"
PYTHON_BIN=""

source "\$APP_RESOURCES/launcher_guard.sh"
pd_require_allowed_parent
pd_init_launch_token
PD_CHILD_PIDS=()
trap 'pd_kill_tracked_children' EXIT INT TERM

case "\$(uname -m)" in
  arm64|aarch64) UV_ARCH="aarch64" ;;
  x86_64) UV_ARCH="x86_64" ;;
  *) UV_ARCH="" ;;
esac
UV_PYTHON=""
if [[ -n "\$UV_ARCH" ]]; then
  UV_PYTHON="\$HOME/.local/share/uv/python/cpython-3.14-macos-\$UV_ARCH-none/bin/python3.14"
fi
cd "\$APP_RESOURCES"
PYTHON_BIN=\$(pd_find_python 'import tkinter' \\
  "\$(printenv PRO_DOWNLOADER_PYTHON || true)" \\
  "\$UV_PYTHON" \\
  "\$ROOT_VENV_PYTHON" \\
  "\${ROOT_VENV_PYTHON%/python}/python3" \\
  "\$(command -v python3 || true)" \\
  "/opt/homebrew/bin/python3" \\
  "/usr/local/bin/python3" \\
  "/usr/bin/python3") || PYTHON_BIN=""

if [[ -z "\$PYTHON_BIN" ]]; then
  osascript -e 'display alert "英文阅读器" message "找不到带 Tk 的 Python 3 环境。请安装 Python 3 或设置 PRO_DOWNLOADER_PYTHON。"' >/dev/null 2>&1 || true
  exit 1
fi

mkdir -p "\$APP_DATA_DIR"
export APP_DATA_DIR="\$APP_DATA_DIR"
export PIPER_MODEL_DIR="\$PIPER_MODEL_DIR"
# 固定句子朗读音色（与 start_ebook_reader.sh 保持一致）：gb→alba，us→lessac。
# 单词音色由 app.py 内的 WORD_VOICE_PREFERENCE 单独挑选（gb→semaine/us→amy），不在此固定。
ALBA_MODEL="\$PIPER_MODEL_DIR/en/en_GB/alba/medium/en_GB-alba-medium.onnx"
if [[ -f "\$ALBA_MODEL" ]]; then
  export PIPER_MODEL="\$ALBA_MODEL"
fi
LESSAC_MODEL="\$PIPER_MODEL_DIR/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
if [[ -f "\$LESSAC_MODEL" ]]; then
  export PIPER_US_MODEL="\$LESSAC_MODEL"
fi
# 优先使用 uv 管理的 piper-tts（onnxruntime 较新，孤立单词合成更稳定/确定性更好）。
if [[ -x "\$HOME/.local/bin/piper" ]]; then
  export PIPER_BIN="\$HOME/.local/bin/piper"
elif [[ -x "\$HOME/.local/share/ebook_reader_piper/bin/piper" ]]; then
  export PIPER_BIN="\$HOME/.local/share/ebook_reader_piper/bin/piper"
  export ESPEAK_DATA_DIR="\$HOME/.local/share/ebook_reader_piper/espeak-ng-data"
fi
export TK_SILENCE_DEPRECATION=1
exec "\$PYTHON_BIN" "\$APP_RESOURCES/app.py" "\$@"
LAUNCHER

chmod +x "$LAUNCHER"

echo "Built: $APP_DIR"
