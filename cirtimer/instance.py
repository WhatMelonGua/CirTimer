"""Tiny file-based command channel between instances (named pipes are blocked
in some environments, and the tray icon can be hidden by Windows)."""
from __future__ import annotations

from pathlib import Path

from .config import data_dir

COMMANDS = ("show", "quit")


def command_path() -> Path:
    return data_dir() / "instance.command"


def send(command: str) -> bool:
    """Ask the running instance to show itself or quit."""
    if command not in COMMANDS:
        return False
    try:
        command_path().write_text(command, encoding="utf-8")
        return True
    except OSError:
        return False


def take() -> str | None:
    """Read and consume a pending command (called by the running instance)."""
    path = command_path()
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        path.unlink()
    except OSError:
        pass
    return text if text in COMMANDS else None
