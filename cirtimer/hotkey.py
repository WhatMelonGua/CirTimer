"""Global hotkey (RegisterHotKey) + time-window scheduling helpers."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, time as dtime

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CTRL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS = {"ctrl": MOD_CTRL, "control": MOD_CTRL, "alt": MOD_ALT,
         "shift": MOD_SHIFT, "win": MOD_WIN, "meta": MOD_WIN}
_KEYS = {chr(c): c for c in range(ord("A"), ord("Z") + 1)}
_KEYS.update({str(d): ord(str(d)) for d in range(10)})
_KEYS.update({"f%d" % i: 0x6F + i for i in range(1, 13)})
_KEYS.update({"space": 0x20, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
              "enter": 0x0D, "insert": 0x2D, "delete": 0x2E,
              "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22})


def parse_hotkey(text: str) -> tuple[int, int] | None:
    """'Ctrl+Alt+M' -> (modifiers, virtual-key). None when unparseable."""
    parts = [p.strip().lower() for p in (text or "").split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    key = None
    for part in parts:
        if part in _MODS:
            mods |= _MODS[part]
        elif part in _KEYS:
            key = _KEYS[part]
        elif len(part) == 1:
            key = ord(part.upper())
    if key is None or mods == 0:
        return None
    return mods, key


class _Filter(QAbstractNativeEventFilter):
    def __init__(self, owner: "GlobalHotkey") -> None:
        super().__init__()
        self._owner = owner

    def nativeEventFilter(self, event_type, message):  # noqa: N802
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == 1:
                    self._owner.pressed.emit()
                    return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkey(QObject):
    """One process-wide hotkey. Registration failures are reported, not raised."""

    pressed = Signal()

    def __init__(self, app, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app = app
        self._filter = _Filter(self)
        self._registered = False
        app.installNativeEventFilter(self._filter)
        self.error = ""

    def register(self, text: str) -> bool:
        self.unregister()
        parsed = parse_hotkey(text)
        if parsed is None:
            self.error = f"无法解析快捷键：{text}"
            return False
        mods, vk = parsed
        try:
            ok = ctypes.windll.user32.RegisterHotKey(None, 1, mods | MOD_NOREPEAT, vk)
        except Exception as exc:  # pragma: no cover - platform specific
            self.error = str(exc)
            return False
        if not ok:
            self.error = "快捷键已被其他程序占用"
            return False
        self._registered = True
        self.error = ""
        return True

    def unregister(self) -> None:
        if self._registered:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, 1)
            except Exception:
                pass
            self._registered = False

    @property
    def registered(self) -> bool:
        return self._registered


# ------------------------------------------------------------- scheduling ---
def parse_hhmm(text: str) -> dtime | None:
    try:
        hh, mm = str(text).split(":")
        return dtime(int(hh), int(mm))
    except Exception:
        return None


def in_schedule(settings, now: datetime | None = None) -> bool:
    """True when *now* falls inside one of the configured work windows."""
    if not getattr(settings, "schedule_enabled", False):
        return False
    now = now or datetime.now()
    iso_weekday = now.isoweekday()          # 1=Mon … 7=Sun
    days = list(getattr(settings, "schedule_days", []) or [])
    if days and iso_weekday not in days:
        return False
    current = now.time()
    for window in getattr(settings, "schedule_windows", []) or []:
        if len(window) != 2:
            continue
        start, end = parse_hhmm(window[0]), parse_hhmm(window[1])
        if start is None or end is None:
            continue
        if start <= current <= end if start <= end else (current >= start or current <= end):
            return True
    return False


def in_dnd(settings, now: datetime | None = None) -> bool:
    if not getattr(settings, "dnd_enabled", False):
        return False
    now = now or datetime.now()
    current = now.time()
    for window in getattr(settings, "dnd_ranges", []) or []:
        if len(window) != 2:
            continue
        start, end = parse_hhmm(window[0]), parse_hhmm(window[1])
        if start is None or end is None:
            continue
        if start <= end:
            if start <= current <= end:
                return True
        elif current >= start or current <= end:      # crosses midnight
            return True
    return False
