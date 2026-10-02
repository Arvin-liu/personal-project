#!/usr/bin/env bash
set -euo pipefail

APP_NAMES=("语言学习器" "英文阅读器")
REMOVED=0

for dir in "/Applications" "$HOME/Applications"; do
  for app_name in "${APP_NAMES[@]}"; do
    app_path="$dir/$app_name.app"
    if [[ -e "$app_path" ]]; then
      rm -rf "$app_path"
      echo "Removed: $app_path"
      REMOVED=1
    fi
  done
done

if [[ "$REMOVED" -eq 0 ]]; then
  echo "No installed app found."
fi
