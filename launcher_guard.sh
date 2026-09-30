#!/usr/bin/env bash
# Minimal launch helpers used by this standalone English Reader project.

pd_parent_command() {
  ps -o comm= -p "${PPID}" 2>/dev/null | awk '{n=$1; sub(".*/", "", n); print n}'
}

pd_require_allowed_parent() {
  local parent_comm
  parent_comm="$(pd_parent_command || true)"
  case "$parent_comm" in
    launchd|Finder|Dock|loginwindow|launchservicesd|open|osascript|SystemUIServer|Automator|Shortcuts|CoreServicesUIAgent)
      return 0
      ;;
    zsh|bash|sh|dash|ksh|fish|python|python3|python3.*|node|npm|codex|Codex|Terminal|iTerm2|Warp|Alacritty|WezTerm|Code|Code\ Helper|Visual\ Studio\ Code)
      echo "[ERROR] Refusing direct launch from parent process: ${parent_comm:-unknown}" >&2
      echo "[ERROR] Start this project from its own launcher or app bundle instead." >&2
      exit 1
      ;;
  esac
  echo "[ERROR] Unable to verify allowed launch parent: ${parent_comm:-unknown}" >&2
  exit 1
}

pd_init_launch_token() {
  local caller_dir token_file token_value
  caller_dir="$(cd "$(dirname "${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}")" && pwd)"
  token_file="${PD_LAUNCH_TOKEN_FILE:-$caller_dir/launch_token.txt}"
  if [[ -z "${PRO_DOWNLOADER_LAUNCH_TOKEN:-}" ]]; then
    if [[ ! -f "$token_file" ]]; then
      echo "[ERROR] Missing launch token file: $token_file" >&2
      echo "[ERROR] Start this project through its own launcher bundle only." >&2
      exit 1
    fi
    token_value="$(tr -d '\r\n' < "$token_file")"
    if [[ -z "$token_value" ]]; then
      echo "[ERROR] Empty launch token file: $token_file" >&2
      exit 1
    fi
    export PRO_DOWNLOADER_LAUNCH_TOKEN="$token_value"
  fi
  if [[ -z "${PRO_DOWNLOADER_LAUNCH_TOKEN:-}" ]]; then
    echo "[ERROR] Launch token missing after initialization." >&2
    exit 1
  fi
}

pd_spawn_managed() {
  local pid
  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" &
  else
    "$@" &
  fi
  pid=$!
  PD_CHILD_PIDS+=("$pid")
  printf '%s\n' "$pid"
}

pd_kill_process_group() {
  local pid=${1:-}
  [[ "$pid" =~ ^[0-9]+$ ]] || return 0
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.1
  done
  kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

pd_kill_tracked_children() {
  local pid
  for pid in "${PD_CHILD_PIDS[@]:-}"; do
    pd_kill_process_group "$pid"
  done
}

pd_notify() {
  local title=$1 body=$2 level=${3:-info}
  case "$(uname -s)" in
    Darwin)
      osascript -e "display notification \"$body\" with title \"$title\"" 2>/dev/null || true
      ;;
    Linux)
      local flags=("-t" "3000")
      [[ "$level" == "error" ]] && flags+=("-u" "critical")
      command -v notify-send >/dev/null 2>&1 && notify-send "${flags[@]}" "$title" "$body" || true
      ;;
  esac
}

pd_find_python() {
  [[ $# -gt 0 ]] || return 1
  local import_probe=$1
  shift
  local candidate resolved
  for candidate in "$@"; do
    [[ -n "$candidate" ]] || continue
    if [[ -x "$candidate" ]]; then
      resolved="$candidate"
    else
      resolved=$(command -v "$candidate" 2>/dev/null || true)
    fi
    [[ -n "$resolved" && -x "$resolved" ]] || continue
    if "$resolved" -c "$import_probe" >/dev/null 2>&1; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}
