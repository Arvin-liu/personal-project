#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source "$SCRIPT_DIR/launcher_guard.sh"
pd_require_allowed_parent
pd_init_launch_token
PD_CHILD_PIDS=()
trap 'pd_kill_tracked_children' EXIT INT TERM

case "$(uname -m)" in
  arm64|aarch64) UV_ARCH="aarch64" ;;
  x86_64) UV_ARCH="x86_64" ;;
  *) UV_ARCH="" ;;
esac
UV_PYTHON=""
if [[ -n "$UV_ARCH" ]]; then
  UV_PYTHON="${HOME}/.local/share/uv/python/cpython-3.14-macos-${UV_ARCH}-none/bin/python3.14"
fi
export APP_DATA_DIR="${APP_DATA_DIR:-${HOME}/Library/Application Support/14_EBook_Reader_Python}"
export PIPER_MODEL_DIR="${APP_DATA_DIR}/piper_models"
# Prefer installed English Piper voices when available; users can set their own models.
ALBA_MODEL="${APP_DATA_DIR}/piper_models/en/en_GB/alba/medium/en_GB-alba-medium.onnx"
if [[ -f "$ALBA_MODEL" ]]; then
  export PIPER_MODEL="$ALBA_MODEL"
fi
LESSAC_MODEL="${APP_DATA_DIR}/piper_models/en/en_US/lessac/medium/en_US-lessac-medium.onnx"
if [[ -f "$LESSAC_MODEL" ]]; then
  export PIPER_US_MODEL="$LESSAC_MODEL"
fi
# Prefer a user-installed Piper runtime and fall back to the optional local installation.
FIXED_PIPER="${HOME}/.local/share/ebook_reader_piper/bin/piper"
if [[ -x "${HOME}/.local/bin/piper" ]]; then
  export PIPER_BIN="${HOME}/.local/bin/piper"
elif [[ -x "$FIXED_PIPER" ]]; then
  export PIPER_BIN="$FIXED_PIPER"
  export ESPEAK_DATA_DIR="${HOME}/.local/share/ebook_reader_piper/espeak-ng-data"
fi
PYTHON_BIN=$(pd_find_python 'import tkinter' \
  "$(printenv PRO_DOWNLOADER_PYTHON || true)" \
  "$UV_PYTHON" \
  "$SCRIPT_DIR/.venv/bin/python3" \
  "$SCRIPT_DIR/.venv/bin/python" \
  "$SCRIPT_DIR/../.venv/bin/python3" \
  "$SCRIPT_DIR/../.venv/bin/python" \
  "$(command -v python3 || true)" \
  "/opt/homebrew/bin/python3" \
  "/usr/local/bin/python3" \
  "/usr/bin/python3") || PYTHON_BIN=""
if [[ -z "$PYTHON_BIN" ]]; then
  pd_notify "语言学习器" "找不到带 Tk 的 Python 3 环境" "error"
  echo "ERROR: Install a Python build with tkinter, or set PRO_DOWNLOADER_PYTHON." >&2
  exit 1
fi

export TK_SILENCE_DEPRECATION=1
child_pid="$(pd_spawn_managed "$PYTHON_BIN" app.py "$@")"
wait "$child_pid"
