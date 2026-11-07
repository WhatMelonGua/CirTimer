"""Independent side reminders: drinking water and eye breaks.

They run alongside the queue rather than inside it, because they fire on their
own rhythm (hydration every N minutes, 20-20-20 every 20 minutes) and must not
consume a queue slot.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal


class SideReminders(QObject):
    water_due = Signal()
    eye_due = Signal()

    def __init__(self, settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._water = QTimer(self)
        self._water.timeout.connect(self._on_water)
        self._eye = QTimer(self)
        self._eye.timeout.connect(self._on_eye)
        self.configure()

    def configure(self) -> None:
        s = self._settings
        if getattr(s, "water_enabled", False):
            minutes = max(15, int(getattr(s, "water_interval_minutes", 60)))
            self._water.start(minutes * 60_000)
        else:
            self._water.stop()

        if getattr(s, "eye_enabled", False):
            self._eye.start(20 * 60_000)          # classic 20-20-20
        else:
            self._eye.stop()

    def start(self) -> None:
        self.configure()

    def stop(self) -> None:
        self._water.stop()
        self._eye.stop()

    # reschedule after a manual reset (e.g. the user drank water)
    def reset_water(self) -> None:
        if self._water.isActive():
            self._water.start(self._water.interval())

    def _on_water(self) -> None:
        self.water_due.emit()

    def _on_eye(self) -> None:
        self.eye_due.emit()
