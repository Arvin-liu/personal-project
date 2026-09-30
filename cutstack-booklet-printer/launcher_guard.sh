#!/usr/bin/env bash
# Small, project-local helpers for the source and macOS launchers.

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
    zsh|bash|sh|dash|ksh|fish|python|python3|python3.*|node|npm|codex|Codex|Terminal|iTerm2|Warp|Alacritty|WezTerm|Code|"Code Helper"|"Visual Studio Code")
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
  token_file="${CUTSTACK_LAUNCH_TOKEN_FILE:-$caller_dir/launch_token.txt}"

  if [[ -z "${CUTSTACK_LAUNCH_TOKEN:-}" ]]; then
    if [[ ! -s "$token_file" ]]; then
      umask 077
      mkdir -p "$(dirname "$token_file")"
      token_value="$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')"
      [[ -n "$token_value" ]] || { echo "[ERROR] Could not create a launch token." >&2; exit 1; }
      printf '%s\n' "$token_value" > "$token_file"
    fi
    token_value="$(tr -d '\r\n' < "$token_file")"
    [[ -n "$token_value" ]] || { echo "[ERROR] Empty launch token file." >&2; exit 1; }
    export CUTSTACK_LAUNCH_TOKEN="$token_value"
  fi
}

pd_find_python() {
  [[ $# -gt 0 ]] || return 1
  local import_probe=$1 candidate resolved
  shift
  for candidate in "$@"; do
    [[ -n "$candidate" ]] || continue
    if [[ -x "$candidate" ]]; then
      resolved="$candidate"
    else
      resolved="$(command -v "$candidate" 2>/dev/null || true)"
    fi
    [[ -n "$resolved" && -x "$resolved" ]] || continue
    if "$resolved" -c "$import_probe" >/dev/null 2>&1; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  return 1
}
