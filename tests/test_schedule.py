"""Schedule / DND / hotkey parsing + snooze-limit behaviour."""
from __future__ import annotations

import os
import sys
import time
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DATA = ROOT / "data" / ".test"
TEST_DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CIRCLOCK_DATA", str(TEST_DATA))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from cirtimer import config, hotkey  # noqa: E402
from cirtimer.engine import ALERT, RUNNING, Engine  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])


@dataclass
class FakeSettings:
    schedule_enabled: bool = True
    schedule_days: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    schedule_windows: list = field(
        default_factory=lambda: [["09:00", "12:00"], ["13:30", "18:30"]])
    dnd_enabled: bool = False
    dnd_ranges: list = field(default_factory=list)


class ScheduleTests(unittest.TestCase):
    def test_inside_work_window(self) -> None:
        s = FakeSettings()
        self.assertTrue(hotkey.in_schedule(s, datetime(2026, 11, 5, 10, 0)))   # Thu
        self.assertTrue(hotkey.in_schedule(s, datetime(2026, 11, 5, 14, 0)))
        self.assertFalse(hotkey.in_schedule(s, datetime(2026, 11, 5, 12, 30)))
        self.assertFalse(hotkey.in_schedule(s, datetime(2026, 11, 5, 8, 59)))

    def test_weekend_is_excluded(self) -> None:
        s = FakeSettings()
        self.assertFalse(hotkey.in_schedule(s, datetime(2026, 11, 7, 10, 0)))  # Sat

    def test_empty_day_list_means_every_day(self) -> None:
        s = FakeSettings(schedule_days=[])
        self.assertTrue(hotkey.in_schedule(s, datetime(2026, 11, 7, 10, 0)))

    def test_disabled_schedule_never_active(self) -> None:
        s = FakeSettings(schedule_enabled=False)
        self.assertFalse(hotkey.in_schedule(s, datetime(2026, 11, 5, 10, 0)))

    def test_dnd_window(self) -> None:
        s = FakeSettings(dnd_enabled=True, dnd_ranges=[["12:00", "13:30"]])
        self.assertTrue(hotkey.in_dnd(s, datetime(2026, 11, 5, 12, 30)))
        self.assertFalse(hotkey.in_dnd(s, datetime(2026, 11, 5, 14, 0)))

    def test_dnd_across_midnight(self) -> None:
        s = FakeSettings(dnd_enabled=True, dnd_ranges=[["23:00", "07:00"]])
        self.assertTrue(hotkey.in_dnd(s, datetime(2026, 11, 5, 23, 30)))
        self.assertTrue(hotkey.in_dnd(s, datetime(2026, 11, 5, 6, 0)))
        self.assertFalse(hotkey.in_dnd(s, datetime(2026, 11, 5, 12, 0)))


class HotkeyParseTests(unittest.TestCase):
    def test_ctrl_alt_m(self) -> None:
        self.assertEqual(hotkey.parse_hotkey("Ctrl+Alt+M"), (0x0002 | 0x0001, ord("M")))

    def test_case_insensitive(self) -> None:
        self.assertEqual(hotkey.parse_hotkey("ctrl+shift+k"),
                         (0x0002 | 0x0004, ord("K")))

    def test_rejects_garbage(self) -> None:
        self.assertIsNone(hotkey.parse_hotkey(""))
        self.assertIsNone(hotkey.parse_hotkey("Ctrl+"))
        self.assertIsNone(hotkey.parse_hotkey("M"))          # needs a modifier


def _queue() -> config.Queue:
    return config.Queue(id="q_snooze", name="S", loop_count=1, rounds=[
        config.Round(name="R", phases=[
            config.Phase(name="A", minutes=1),
            config.Phase(name="B", minutes=1),
        ])])


class SnoozeLimitTests(unittest.TestCase):
    def _engine(self, limit: int) -> Engine:
        cfg = config.Config(settings=config.Settings(snooze_limit=limit,
                                                     snooze_minutes=1),
                            queues=[_queue()], current_queue="q_snooze")
        cfg.settings.default_queue = "q_snooze"
        return Engine(cfg)

    def _expire(self, eng: Engine) -> None:
        eng._deadline = time.monotonic() - 0.01
        eng._on_tick()

    def test_snooze_allowed_then_blocked(self) -> None:
        eng = self._engine(1)
        eng.start()
        self._expire(eng)
        self.assertEqual(eng.state, ALERT)
        self.assertTrue(eng.can_snooze())
        eng.ack("snooze")
        self.assertEqual(eng.phase.name, "A")
        self._expire(eng)
        self.assertFalse(eng.can_snooze())
        eng.ack("snooze")                 # blocked -> advances instead
        self.assertEqual(eng.phase.name, "B")
        eng.stop(record=False)

    def test_limit_zero_disallows_snooze(self) -> None:
        eng = self._engine(0)
        eng.start()
        self._expire(eng)
        self.assertFalse(eng.can_snooze())
        eng.ack("snooze")
        self.assertEqual(eng.phase.name, "B")
        eng.stop(record=False)

    def test_counter_resets_on_new_phase(self) -> None:
        eng = self._engine(2)
        eng.start()
        self._expire(eng)
        eng.ack("snooze")
        self.assertEqual(eng.snoozes_used(), 1)
        eng.skip()
        self.assertEqual(eng.snoozes_used(), 0)
        eng.stop(record=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
