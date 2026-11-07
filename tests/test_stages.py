"""Entry / exit stages and the "loop until a clock time" mode."""
from __future__ import annotations

import os
import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DATA = ROOT / "data" / ".test"
TEST_DATA.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("CIRCLOCK_DATA", str(TEST_DATA))

from PySide6.QtCore import QCoreApplication  # noqa: E402

from cirtimer import config  # noqa: E402
from cirtimer.engine import IDLE, STAGE_ENTRY, STAGE_EXIT, STAGE_LOOP, Engine  # noqa: E402

APP = QCoreApplication.instance() or QCoreApplication([])


def ph(name: str) -> config.Phase:
    return config.Phase(name=name, minutes=1)


def make_queue(**kw) -> config.Queue:
    kw.setdefault("loop_count", 1)
    return config.Queue(id="q_stage", name="Q",
                        rounds=[config.Round(name="R", phases=[ph("A"), ph("B")])], **kw)


def make_engine(queue: config.Queue) -> Engine:
    cfg = config.Config(settings=config.Settings(), queues=[queue], current_queue=queue.id)
    cfg.settings.default_queue = queue.id
    return Engine(cfg)


def expire(engine: Engine) -> None:
    engine._deadline = time.monotonic() - 0.01
    engine._on_tick()


class StageOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.queue = make_queue(entry=[ph("E")], exit=[ph("X")])
        self.eng = make_engine(self.queue)
        self.finished: list[bool] = []
        self.eng.queue_finished.connect(lambda: self.finished.append(True))

    def tearDown(self) -> None:
        self.eng.stop(record=False)

    def names(self) -> list[str]:
        return []

    def run_phase(self, expected: str) -> None:
        self.assertEqual(self.eng.phase.name, expected)
        expire(self.eng)
        self.eng.ack("next")

    def test_entry_then_loop_then_exit(self) -> None:
        self.eng.start()
        self.assertEqual(self.eng.stage, STAGE_ENTRY)
        self.run_phase("E")
        self.assertEqual(self.eng.stage, STAGE_LOOP)
        self.run_phase("A")
        self.run_phase("B")
        self.assertEqual(self.eng.stage, STAGE_EXIT)
        self.run_phase("X")
        self.assertEqual(self.eng.state, IDLE)
        self.assertTrue(self.finished)

    def test_no_exit_when_empty(self) -> None:
        eng = make_engine(make_queue(entry=[ph("E")]))
        eng.start()
        expire(eng)
        eng.ack("next")          # E -> A
        expire(eng)
        eng.ack("next")          # A -> B
        expire(eng)
        eng.ack("next")          # B -> finished (no exit stages)
        self.assertEqual(eng.state, IDLE)
        eng.stop(record=False)

    def test_two_passes_before_exit(self) -> None:
        queue = make_queue(loop_count=2, exit=[ph("X")])
        eng = make_engine(queue)
        seen = []
        eng.phase_changed.connect(lambda phase, info: seen.append(phase.name))
        eng.start()
        for _ in range(4):          # A B A B
            expire(eng)
            eng.ack("next")
        self.assertEqual(seen, ["A", "B", "A", "B", "X"])
        eng.stop(record=False)


class UntilModeTests(unittest.TestCase):
    def test_deadline_already_passed_runs_one_pass(self) -> None:
        queue = make_queue(loop_mode="until", until_time="00:00", exit=[ph("X")])
        eng = make_engine(queue)
        seen = []
        eng.phase_changed.connect(lambda phase, info: seen.append(phase.name))
        eng.start()
        self.assertIsNotNone(eng.until_deadline())
        for _ in range(2):
            expire(eng)
            eng.ack("next")
        self.assertEqual(seen, ["A", "B", "X"])
        eng.stop(record=False)

    def test_deadline_in_future_keeps_looping(self) -> None:
        queue = make_queue(loop_mode="until", until_time="23:59")
        eng = make_engine(queue)
        seen: list[str] = []
        eng.phase_changed.connect(lambda phase, info: seen.append(phase.name))
        eng.start()
        eng._until = datetime.now() + timedelta(hours=2)
        for _ in range(2):          # finish the first pass
            expire(eng)
            eng.ack("next")
        for _ in range(2):          # second pass: must stay in the loop
            expire(eng)
            eng.ack("next")
        # the fifth entry is pass 3 starting: the loop kept going instead of exiting
        self.assertEqual(seen, ["A", "B", "A", "B", "A"])
        self.assertEqual(eng.info()["loop"], 3)
        eng._until = datetime.now() - timedelta(minutes=1)
        expire(eng)
        eng.ack("next")
        expire(eng)
        eng.ack("next")
        self.assertEqual(eng.state, IDLE)
        eng.stop(record=False)

    def test_forever_never_finishes(self) -> None:
        queue = make_queue(loop_mode="forever")
        eng = make_engine(queue)
        finished = []
        eng.queue_finished.connect(lambda: finished.append(True))
        eng.start()
        for _ in range(6):
            expire(eng)
            eng.ack("next")
        self.assertFalse(finished)
        self.assertEqual(eng.info()["loop"], 4)
        eng.stop(record=False)

    def test_until_remaining_counts_down(self) -> None:
        queue = make_queue(loop_mode="until", until_time="23:59")
        eng = make_engine(queue)
        eng.start()
        eng._until = datetime.now() + timedelta(minutes=10)
        remaining = eng.until_remaining()
        self.assertTrue(570 < remaining <= 600, remaining)
        eng.stop(record=False)


class LoopLabelTests(unittest.TestCase):
    def test_labels(self) -> None:
        self.assertEqual(make_queue(loop_count=3).loop_label(), "循环 3 轮")
        self.assertEqual(make_queue(loop_mode="forever").loop_label(), "无限循环")
        self.assertEqual(make_queue(loop_mode="until", until_time="18:30").loop_label(),
                         "循环到 18:30")


class QueueSerialisationTests(unittest.TestCase):
    def test_entry_exit_and_mode_round_trip(self) -> None:
        queue = make_queue(entry=[ph("E")], exit=[ph("X")],
                           loop_mode="until", until_time="20:00")
        restored = config.Queue.from_dict(queue.to_dict())
        self.assertEqual(restored.loop_mode, "until")
        self.assertEqual(restored.until_time, "20:00")
        self.assertEqual([p.name for p in restored.entry], ["E"])
        self.assertEqual([p.name for p in restored.exit], ["X"])

    def test_old_config_without_mode_still_loads(self) -> None:
        data = {"id": "old", "name": "Old", "loop_count": 0,
                "rounds": [{"name": "R", "phases": []}]}
        restored = config.Queue.from_dict(data)
        self.assertEqual(restored.loop_mode, "forever")
        self.assertEqual(restored.entry, [])
        self.assertEqual(restored.exit, [])

    def test_parse_hhmm_datetime(self) -> None:
        value = config.parse_hhmm_datetime("20:00")
        self.assertIsNotNone(value)
        self.assertEqual((value.hour, value.minute), (20, 0))
        self.assertIsNone(config.parse_hhmm_datetime("nonsense"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
