#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/launcher_guard.sh"
pd_init_launch_token
cd "$SCRIPT_DIR"

PYTHON_BIN="$(pd_find_python 'import ui' \
  "$(printenv CUTSTACK_PYTHON || true)" \
  "$SCRIPT_DIR/.venv/bin/python" \
  "$(command -v python3 || true)" \
  "/opt/homebrew/bin/python3" \
  "/usr/local/bin/python3" \
  "/usr/bin/python3")" || PYTHON_BIN=""

if [[ -z "$PYTHON_BIN" ]]; then
  echo "No Python interpreter with the required app dependencies was found." >&2
  echo "Create .venv and install requirements.txt, or set CUTSTACK_PYTHON." >&2
  exit 1
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  export TK_SILENCE_DEPRECATION=1
fi
exec "$PYTHON_BIN" "$SCRIPT_DIR/main.py" "$@"
