"""Idle detection (Windows GetLastInputInfo) and presence bookkeeping."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, QTimer, Signal


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input in this session."""
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return 0.0
        now = ctypes.windll.kernel32.GetTickCount()
        delta = (int(now) - int(info.dwTime)) & 0xFFFFFFFF
        return delta / 1000.0
    except Exception:
        return 0.0


class PresenceWatcher(QObject):
    """Emits ``away`` once the user has been idle past the threshold.

    The threshold is read from settings on every poll so the UI can change it
    without rewiring anything.
    """

    away = Signal(float)          # idle seconds when the user left
    back = Signal(float)          # how long the user was away

    def __init__(self, settings, parent: QObject | None = None, interval_ms: int = 3000):
        super().__init__(parent)
        self._settings = settings
        self._away = False
        self._away_started = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    @property
    def is_away(self) -> bool:
        return self._away

    def _poll(self) -> None:
        if not getattr(self._settings, "auto_pause_on_idle", True):
            if self._away:
                self._away = False
            return
        limit = max(30, int(getattr(self._settings, "idle_seconds", 180)))
        idle = idle_seconds()
        if not self._away and idle >= limit:
            self._away = True
            self._away_started = time.monotonic() - idle
            self.away.emit(idle)
        elif self._away and idle < 3.0:
            self._away = False
            duration = time.monotonic() - self._away_started
            self.back.emit(duration)
