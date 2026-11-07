"""Engine + config tests (stdlib unittest, no pytest needed).

Run:  envs\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# keep test runs out of the real history database
TEST_DATA = ROOT / "data" / ".test"
TEST_DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CIRCLOCK_DATA", str(TEST_DATA))
for stale in TEST_DATA.glob("history.db"):
    try:
        stale.unlink()
    except OSError:
        pass

from PySide6.QtCore import QCoreApplication  # noqa: E402

from cirtimer import config, stats  # noqa: E402
from cirtimer.engine import ALERT, IDLE, PAUSED, RUNNING, Engine  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])


def make_queue(phase_seconds: float = 60.0, count: int = 2, loop: int = 1) -> config.Queue:
    phases = [
        config.Phase(name=f"P{i}", kind="focus", minutes=phase_seconds / 60.0)
        for i in range(count)
    ]
    return config.Queue(id=f"q_test_{count}_{loop}", name="Test", loop_count=loop,
                        rounds=[config.Round(name="R1", phases=phases)])


def make_cfg(queue: config.Queue) -> config.Config:
    cfg = config.Config(settings=config.Settings(), queues=[queue], current_queue=queue.id)
    cfg.settings.default_queue = queue.id
    return cfg


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queue = make_queue()
        self.cfg = make_cfg(self.queue)
        self.eng = Engine(self.cfg)
        self.states: list[str] = []
        self.eng.state_changed.connect(self.states.append)

    def tearDown(self) -> None:
        self.eng.stop(record=False)

    def _expire(self) -> None:
        self.eng._deadline = time.monotonic() - 0.01
        self.eng._on_tick()

    def test_starts_running_on_first_phase(self) -> None:
        self.eng.start()
        self.assertEqual(self.eng.state, RUNNING)
        self.assertEqual(self.eng.phase.name, "P0")
        self.assertEqual(self.eng.info()["index"], 1)
        self.assertEqual(self.eng.info()["count"], 2)

    def test_phase_end_waits_for_ack_then_advances(self) -> None:
        self.eng.start()
        self._expire()
        self.assertEqual(self.eng.state, ALERT)
        self.assertEqual(self.eng.phase.name, "P0")
        self.eng.ack("next")
        self.assertEqual(self.eng.state, RUNNING)
        self.assertEqual(self.eng.phase.name, "P1")

    def test_loops_then_finishes(self) -> None:
        queue = make_queue(count=2, loop=2)
        cfg = make_cfg(queue)
        eng = Engine(cfg)
        finished: list[bool] = []
        eng.queue_finished.connect(lambda: finished.append(True))
        eng.start()
        for _ in range(4):
            self._expire_for(eng)
            eng.ack("next")
        self.assertTrue(finished)
        self.assertEqual(eng.state, IDLE)

    @staticmethod
    def _expire_for(eng: Engine) -> None:
        eng._deadline = time.monotonic() - 0.01
        eng._on_tick()

    def test_skip_advances_without_alert(self) -> None:
        self.eng.start()
        self.eng.skip()
        self.assertEqual(self.eng.state, RUNNING)
        self.assertEqual(self.eng.phase.name, "P1")

    def test_skip_settles_as_skipped(self) -> None:
        self.eng.start()
        self.eng.skip()
        summary = stats.today_summary()
        self.assertGreaterEqual(summary["skips"], 1)

    def test_pause_keeps_remaining_and_resumes(self) -> None:
        self.eng.start()
        self.eng._deadline = time.monotonic() + 30.0
        self.eng.pause()
        self.assertEqual(self.eng.state, PAUSED)
        left = self.eng.remaining()
        self.assertTrue(28.0 < left <= 30.0, left)
        time.sleep(0.05)
        self.assertAlmostEqual(self.eng.remaining(), left, delta=0.02)
        self.eng.resume()
        self.assertEqual(self.eng.state, RUNNING)
        self.assertAlmostEqual(self.eng.remaining(), left, delta=0.2)

    def test_snooze_extends_current_phase(self) -> None:
        self.cfg.settings.snooze_minutes = 1
        self.eng.start()
        self._expire()
        self.assertEqual(self.eng.state, ALERT)
        self.eng.ack("snooze")
        self.assertEqual(self.eng.state, RUNNING)
        self.assertEqual(self.eng.phase.name, "P0")
        self.assertGreater(self.eng.remaining(), 55.0)

    def test_stop_returns_to_idle(self) -> None:
        self.eng.start()
        self.eng.stop()
        self.assertEqual(self.eng.state, IDLE)
        self.assertIsNone(self.eng.phase)

    def test_next_phase_reports_end_of_queue(self) -> None:
        queue = make_queue(count=1, loop=1)
        eng = Engine(make_cfg(queue))
        eng.start()
        self.assertIsNone(eng.next_phase())
        eng.stop(record=False)


class PhaseTests(unittest.TestCase):
    def test_fixed_duration(self) -> None:
        ph = config.Phase(minutes=2)
        self.assertEqual(ph.resolve_seconds(), 120.0)

    def test_range_duration_is_within_bounds(self) -> None:
        ph = config.Phase(use_range=True, minutes_min=1, minutes_max=3)
        for _ in range(50):
            secs = ph.resolve_seconds()
            self.assertGreaterEqual(secs, 60.0)
            self.assertLessEqual(secs, 180.0)

    def test_minimum_duration_clamped(self) -> None:
        ph = config.Phase(minutes=0)
        self.assertGreaterEqual(ph.resolve_seconds(), 5.0)


class ConfigTests(unittest.TestCase):
    def test_round_trip_preserves_queues_and_hooks(self) -> None:
        cfg = config.Config(queues=config.default_queues(), current_queue="q_sit")
        cfg.queues[0].rounds[0].phases[0].hooks_start.append(
            config.Hook(type="open", target="https://example.com"))
        cfg.settings.theme = "neon-dark"
        cfg.settings.volume = 42

        restored = config.Config.from_dict(cfg.to_dict())
        self.assertEqual(restored.settings.theme, "neon-dark")
        self.assertEqual(restored.settings.volume, 42)
        self.assertEqual(restored.current_queue, "q_sit")
        hook = restored.queues[0].rounds[0].phases[0].hooks_start[0]
        self.assertEqual(hook.target, "https://example.com")
        self.assertEqual(len(restored.queues), len(config.default_queues()))

    def test_save_and_load(self) -> None:
        cfg = config.load()
        cfg.settings.snooze_limit = 3
        config.save(cfg)
        again = config.load()
        self.assertEqual(again.settings.snooze_limit, 3)

    def test_unknown_current_queue_falls_back(self) -> None:
        cfg = config.Config(queues=config.default_queues(), current_queue="nope")
        self.assertIsNotNone(cfg.current())


if __name__ == "__main__":
    unittest.main(verbosity=2)
