#!/usr/bin/env python3
# Version: 1.0.0 (2026-04-17 00:00) - Linux print helpers
"""Preview and print helpers for the imposed PDF."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class PrintCommandError(RuntimeError):
    """Raised when a preview or print command fails."""


def _has_poppler_binaries(directory: Path) -> bool:
    """Return whether a directory contains the two tools pdf2image needs."""

    return all(
        (directory / executable).is_file()
        and os.access(directory / executable, os.X_OK)
        for executable in ("pdftoppm", "pdfinfo")
    )


def _append_unique_path(candidates: list[Path], path: Path | None) -> None:
    """Append one normalized candidate path without duplicating it."""

    if path is None:
        return
    candidate = path.expanduser()
    if candidate.is_file():
        candidate = candidate.parent
    if candidate not in candidates:
        candidates.append(candidate)


def get_poppler_path() -> Path | None:
    """Locate a Poppler bin directory for pdf2image.

    GUI applications launched by macOS LaunchServices do not inherit the
    interactive shell's PATH.  Check an explicit override, the current PATH,
    common Homebrew/MacPorts locations, and Homebrew's own prefix lookup so
    the in-app PDF preview works from Finder as well as from a terminal.
    """

    candidates: list[Path] = []
    for variable_name in ("CUTSTACK_POPPLER_PATH", "POPPLER_PATH"):
        _append_unique_path(candidates, Path(os.environ[variable_name]) if os.environ.get(variable_name) else None)

    for executable_name in ("pdftoppm", "pdfinfo"):
        executable = shutil.which(executable_name)
        _append_unique_path(candidates, Path(executable) if executable else None)

    home = Path.home()
    candidates.extend(
        path
        for path in (
            Path("/opt/homebrew/opt/poppler/bin"),
            Path("/usr/local/opt/poppler/bin"),
            Path("/opt/local/bin"),
            home / "homebrew/opt/poppler/bin",
            home / ".linuxbrew/opt/poppler/bin",
            home / "homebrew/bin",
        )
        if path not in candidates
    )

    brew_candidates: list[Path] = []
    for brew_path in (
        shutil.which("brew"),
        "/opt/homebrew/bin/brew",
        "/usr/local/bin/brew",
        str(home / "homebrew/bin/brew"),
        str(home / ".linuxbrew/bin/brew"),
    ):
        if brew_path:
            _append_unique_path(brew_candidates, Path(brew_path))

    for brew in brew_candidates:
        if not brew.is_file() or not os.access(brew, os.X_OK):
            continue
        try:
            result = subprocess.run(
                [str(brew), "--prefix", "poppler"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        prefix = result.stdout.strip()
        if result.returncode == 0 and prefix:
            _append_unique_path(candidates, Path(prefix) / "bin")

    for candidate in candidates:
        if _has_poppler_binaries(candidate):
            return candidate.resolve()
    return None


def validate_output_path(path: Path) -> Path:
    """Ensure the output file or folder exists before opening or printing it."""

    resolved = path.expanduser().resolve()
    if not resolved.exists():
        raise PrintCommandError(f"目标不存在：{resolved}")
    return resolved


def _get_open_commands(path: Path) -> list[list[str]]:
    """Return desktop open commands in platform priority order."""

    target = str(path)
    commands = []
    # macOS 原生 open 优先；Linux 继续支持 xdg-open 和 gio。
    if shutil.which("open"):
        commands.append(["open", target])
    if shutil.which("xdg-open"):
        commands.append(["xdg-open", target])
    if shutil.which("gio"):
        commands.append(["gio", "open", target])
    return commands


def get_open_command(path: Path) -> list[str]:
    """Return the preferred command for opening a file or directory.

    This small public helper keeps the macOS preference explicit and makes the
    platform selection independently testable without opening a real desktop
    window.
    """

    commands = _get_open_commands(path)
    if not commands:
        raise PrintCommandError("系统缺少 open、xdg-open 或 gio，无法打开文件。")
    return commands[0]


def open_path_with_default_app(path: Path) -> None:
    """Open a file or directory with the desktop's default application."""

    target = validate_output_path(path)
    commands = _get_open_commands(target)
    if not commands:
        raise PrintCommandError("系统缺少 open、xdg-open 或 gio，无法打开文件。")

    last_error: Exception | None = None
    for command in commands:
        try:
            subprocess.Popen(command)
            return
        except OSError as exc:  # pragma: no cover - desktop-specific
            last_error = exc

    raise PrintCommandError(f"打开失败：{last_error}")


def direct_print_pdf(
    pdf_path: Path,
    printer_name: str | None = None,
    sides: str = "two-sided-long-edge",
    copies: int = 1,
    number_up: int = 1,
) -> None:
    """Send the PDF to CUPS as an explicit, immediate print request.

    ``number_up`` must stay at 1 because the PDF is already laid out for the
    selected print mode. The standard IPP ``sides`` option is accompanied by
    an explicit CUPS ``Duplex`` value for queues that do not apply the IPP
    setting by themselves. ``fit-to-page`` and
    ``print-scaling=fit`` let the printer/CUPS filter scale and center the PDF
    inside the selected media's imageable area instead of clipping A4 edges.
    """

    target = validate_output_path(pdf_path)
    lp_bin = shutil.which("lp")
    if not lp_bin:
        raise PrintCommandError("未找到 lp 命令，请先安装并启用 CUPS。")
    if copies < 1:
        raise PrintCommandError("打印份数必须大于等于 1。")
    if number_up < 1:
        raise PrintCommandError("number-up 必须大于等于 1。")

    duplex_options = {
        "one-sided": "None",
        "two-sided-long-edge": "DuplexNoTumble",
        "two-sided-short-edge": "DuplexTumble",
    }
    ppd_duplex = duplex_options.get(sides)
    if ppd_duplex is None:
        raise PrintCommandError(f"不支持的双面方式：{sides}")

    command = [lp_bin, "-H", "immediate"]
    if printer_name:
        command.extend(["-d", printer_name])
    command.extend(
        [
            "-n",
            str(copies),
            "-o",
            "media=A4",
            "-o",
            "fit-to-page=true",
            "-o",
            "print-scaling=fit",
            "-o",
            f"sides={sides}",
            "-o",
            f"Duplex={ppd_duplex}",
            "-o",
            f"number-up={number_up}",
            str(target),
        ]
    )

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise PrintCommandError(f"打印失败：{message}") from exc


def open_pdf_for_manual_print(pdf_path: Path) -> None:
    """Open the imposed PDF so the user can print it from the PDF viewer."""

    open_path_with_default_app(pdf_path)
