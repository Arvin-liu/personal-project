#!/usr/bin/env python3
# Version: 1.0.0 (2026-04-17 00:00) - cutstack-booklet-printer
"""Entry point for the CutStack Booklet Printer desktop app."""

import os
import fcntl
import subprocess
import sys
from pathlib import Path

from ui import launch_app

APP_NAME = "CutStack Booklet Printer"
LAUNCH_TOKEN_FILENAME = "launch_token.txt"
LOCK_PATH = Path.home() / ".config" / "cutstack-booklet-printer" / "instance.lock"
LAUNCH_LOCK_HANDLE = None


def require_launch_token() -> None:
    token = os.environ.get("CUTSTACK_LAUNCH_TOKEN", "").strip()
    token_file = Path(__file__).resolve().parent / LAUNCH_TOKEN_FILENAME
    if not token_file.exists():
        raise RuntimeError("启动被拒绝：缺少启动令牌，只能通过项目自己的启动器启动 CutStack Booklet Printer。")
    expected = token_file.read_text(encoding="utf-8", errors="replace").strip()
    if not token or not expected or token != expected:
        raise RuntimeError("启动被拒绝：启动令牌无效，只能通过项目自己的启动器启动 CutStack Booklet Printer。")


def acquire_single_instance_lock() -> None:
    global LAUNCH_LOCK_HANDLE

    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_PATH.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("启动被拒绝：CutStack Booklet Printer 已经在运行，只允许保留一个实例。") from exc

    handle.seek(0)
    handle.truncate()
    handle.write(f"{os.getpid()}\n")
    handle.flush()
    LAUNCH_LOCK_HANDLE = handle


def notify_startup_error(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    if sys.platform != "darwin":
        return
    escaped_message = message.replace("\\", "\\\\").replace('"', '\\"')
    escaped_title = APP_NAME.replace("\\", "\\\\").replace('"', '\\"')
    try:
        subprocess.run(
            ["osascript", "-e", f'display alert "{escaped_title}" message "{escaped_message}"'],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


if __name__ == "__main__":
    try:
        require_launch_token()
        acquire_single_instance_lock()
        launch_app()
    except RuntimeError as exc:
        notify_startup_error(str(exc))
        raise SystemExit(1) from exc
