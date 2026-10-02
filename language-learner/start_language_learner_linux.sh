#!/usr/bin/env bash
# Language Learner launcher for Linux
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
source "$SCRIPT_DIR/launcher_guard.sh"
pd_require_allowed_parent
pd_init_launch_token
PD_CHILD_PIDS=()
trap 'pd_kill_tracked_children' EXIT INT TERM

export APP_DATA_DIR="${APP_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/14_EBook_Reader_Python}"
export TK_SILENCE_DEPRECATION=1

# Prefer venv python if available, fallback to system python3
PYTHON_BIN=""
if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "ERROR: python3 not found" >&2
  exit 1
fi

child_pid="$(pd_spawn_managed "$PYTHON_BIN" app.py "$@")"
wait "$child_pid"
