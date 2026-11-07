"""Launch-at-login registration.

Windows: ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
Linux:   ``~/.config/autostart/circlock.desktop``
macOS:   not implemented (returns False, the checkbox simply won't stick)
"""
from __future__ import annotations

import sys
from pathlib import Path

try:  # pragma: no cover - Windows only
    import winreg
except Exception:  # pragma: no cover
    winreg = None  # type: ignore[assignment]

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CirClock"

DESKTOP_NAME = "circlock.desktop"


def _entry_script() -> Path:
    return Path(__file__).resolve().parent.parent / "CirClock.pyw"


def _command() -> str:
    entry = _entry_script()
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if not pythonw.exists():
        pythonw = exe
    return f'"{pythonw}" "{entry}"'


# ------------------------------------------------------------------- linux ---
def _desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / DESKTOP_NAME


def _linux_enable() -> bool:
    path = _desktop_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=超能苹果钟\n"
            "Comment=工位节律闹钟\n"
            f"Exec=\"{sys.executable}\" \"{_entry_script()}\"\n"
            "X-GNOME-Autostart-enabled=true\n"
            "Terminal=false\n",
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def _linux_disable() -> bool:
    try:
        _desktop_path().unlink(missing_ok=True)
        return True
    except OSError:
        return False


# ------------------------------------------------------------------ public ---
def is_enabled() -> bool:
    if sys.platform == "linux":
        return _desktop_path().is_file()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except Exception:
        return False


def enable() -> bool:
    if sys.platform == "linux":
        return _linux_enable()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
        return True
    except Exception:
        # sandboxed / locked-down accounts: fail quietly, the checkbox just won't stick
        return False


def disable() -> bool:
    if sys.platform == "linux":
        return _linux_disable()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


def apply(enabled: bool) -> bool:
    return enable() if enabled else disable()
