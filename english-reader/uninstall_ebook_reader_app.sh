#!/usr/bin/env bash
set -euo pipefail

APP_NAME="英文阅读器"
REMOVED=0

for dir in "/Applications" "$HOME/Applications"; do
  app_path="$dir/$APP_NAME.app"
  if [[ -e "$app_path" ]]; then
    rm -rf "$app_path"
    echo "Removed: $app_path"
    REMOVED=1
  fi
done

if [[ "$REMOVED" -eq 0 ]]; then
  echo "No installed app found."
fi
