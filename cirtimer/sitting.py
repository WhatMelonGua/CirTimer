"""Continuous sitting clock — independent from the queue.

The queue says when a break *should* happen; this clock measures how long the
body has actually been in the chair, which is what the health advice cares
about. Time only accumulates while the user is present.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import stats


class SittingTracker(QObject):
    tick = Signal(float)          # current continuous sitting, minutes
    over_limit = Signal(float)    # fired once when the limit is crossed

    def __init__(self, settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._seconds = 0.0
        self._last = time.monotonic()
        self._present = True
        self._notified = False
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._poll)

    # -- lifecycle
    def start(self) -> None:
        self._last = time.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    # -- presence
    def set_present(self, present: bool) -> None:
        self._flush()
        if present and not self._present:
            self._last = time.monotonic()
        self._present = present

    # -- values
    def minutes(self) -> float:
        return self._seconds / 60.0

    def reset(self) -> None:
        """Called when the user confirms standing up."""
        if self._seconds >= 30:
            stats.record_presence("sit", self._seconds, "stood up")
        self._seconds = 0.0
        self._notified = False
        self._last = time.monotonic()
        self.tick.emit(0.0)

    # -- internals
    def _flush(self) -> None:
        now = time.monotonic()
        delta = max(0.0, now - self._last)
        self._last = now
        if self._present:
            self._seconds += delta

    def _poll(self) -> None:
        self._flush()
        self.tick.emit(self.minutes())
        limit = max(5, int(getattr(self._settings, "sitting_limit_minutes", 50))) * 60.0
        if self._seconds >= limit and not self._notified:
            self._notified = True
            self.over_limit.emit(self.minutes())
