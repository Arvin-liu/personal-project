#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_SCRIPT="$ROOT_DIR/build_ebook_reader_app.sh"
APP_NAME="英文阅读器"
SOURCE_APP="$ROOT_DIR/$APP_NAME.app"
PRIMARY_DEST="/Applications"
FALLBACK_DEST="$HOME/Applications"

"$BUILD_SCRIPT"

DEST_DIR="$PRIMARY_DEST"
if [[ ! -w "$PRIMARY_DEST" ]]; then
  mkdir -p "$FALLBACK_DEST"
  DEST_DIR="$FALLBACK_DEST"
fi

DEST_APP="$DEST_DIR/$APP_NAME.app"
# 关键：先杀掉正在运行的旧实例，否则 macOS 的 open 只会聚焦内存里跑旧代码的实例，
# 磁盘上的新文件不会生效（表现为"刷新后未显示更新"）。pkill 找不到进程时返回非 0，
# 在 set -e 下要用 || true 兜底。
pkill -f "$APP_NAME.app/Contents/Resources/app.py" 2>/dev/null || true
sleep 1
rm -rf "$DEST_APP"
cp -R "$SOURCE_APP" "$DEST_DIR/"
open "$DEST_APP" >/dev/null 2>&1 || true

echo "Installed to: $DEST_APP"
