"""Queue / timer state machine. Pure logic, no widgets — unit-testable.

A queue plays three ordered groups:

    entry  (起始阶段, run once)
    loop   (all rounds, flattened, repeated according to ``loop_mode``)
    exit   (结束阶段, run once)

``loop_mode`` is ``count`` (N passes), ``forever`` or ``until`` (repeat until a
wall-clock time such as 18:30). The ``until`` mode is what lets a daily plan say
"keep cycling until 20:00, then run the closing stages".
"""
from __future__ import annotations

import random
import time
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from . import config, hooks, stats

IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"
ALERT = "alert"

STAGE_ENTRY = "entry"
STAGE_LOOP = "loop"
STAGE_EXIT = "exit"

STAGE_LABELS = {STAGE_ENTRY: "起始阶段", STAGE_LOOP: "循环", STAGE_EXIT: "结束阶段"}


class Engine(QObject):
    """Walks a queue: entry stages -> rounds repeated -> exit stages.

    Signals
    -------
    tick(remaining, total)      once per ~100 ms while running
    phase_changed(phase, info)  a new phase became current
    state_changed(state)        idle / running / paused / alert
    pre_alert(phase)            soft warning a bit before the phase ends
    alert(phase, info)          phase settled, waiting for acknowledgement
    queue_finished()            entry + loops + exit are all done
    stage_changed(stage)        "entry" / "loop" / "exit"
    """

    tick = Signal(float, float)
    phase_changed = Signal(object, dict)
    state_changed = Signal(str)
    pre_alert = Signal(object)
    alert = Signal(object, dict)
    queue_finished = Signal()
    stage_changed = Signal(str)

    def __init__(self, cfg: config.Config, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._queue: config.Queue = cfg.current()

        self._entry: list[config.Phase] = []
        self._loop: list[tuple[str, config.Phase]] = []     # (round name, phase)
        self._exit: list[config.Phase] = []

        self._stage = STAGE_ENTRY
        self._idx = -1
        self._pass = 1
        self._until: datetime | None = None

        self._phase: config.Phase | None = None
        self._total = 0.0
        self._deadline = 0.0
        self._started_at = 0.0
        self._paused_left = 0.0
        self._state = IDLE
        self._pre_done = False
        self._snoozes = 0
        self._stopped = False

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._on_tick)

        self._pre = QTimer(self)
        self._pre.setSingleShot(True)
        self._pre.timeout.connect(self._on_pre_alert)

    # ------------------------------------------------------------- access ---
    @property
    def state(self) -> str:
        return self._state

    @property
    def phase(self) -> config.Phase | None:
        return self._phase

    @property
    def queue(self) -> config.Queue:
        return self._queue

    @property
    def stage(self) -> str:
        return self._stage

    def remaining(self) -> float:
        if self._state == RUNNING:
            return max(0.0, self._deadline - time.monotonic())
        if self._state == PAUSED:
            return max(0.0, self._paused_left)
        return 0.0

    def progress(self) -> float:
        if self._total <= 0:
            return 0.0
        return 1.0 - min(1.0, max(0.0, self.remaining() / self._total))

    def can_snooze(self) -> bool:
        """Whether the current phase may still be postponed."""
        limit = int(self.cfg.settings.snooze_limit)
        return limit > 0 and self._snoozes < limit

    def was_stopped(self) -> bool:
        """True when the user pressed 停止 (so the UI can say so)."""
        return self._stopped

    def snoozes_used(self) -> int:
        return self._snoozes

    def current_list(self) -> list:
        if self._stage == STAGE_ENTRY:
            return self._entry
        if self._stage == STAGE_EXIT:
            return self._exit
        return self._loop

    def stage_label(self) -> str:
        return STAGE_LABELS.get(self._stage, self._stage)

    def until_deadline(self) -> datetime | None:
        return self._until

    def until_remaining(self) -> float | None:
        if self._until is None:
            return None
        return max(0.0, (self._until - datetime.now()).total_seconds())

    def info(self) -> dict:
        current = self.current_list()
        n = len(current)
        rnd_name = ""
        if self._stage == STAGE_LOOP and 0 <= self._idx < len(self._loop):
            rnd_name = self._loop[self._idx][0]
        return {
            "index": self._idx + 1 if self._idx >= 0 else 0,
            "count": n,
            "loop": self._pass,
            "loop_count": self._queue.loop_count,
            "loop_mode": self._queue.loop_mode,
            "until_time": self._queue.until_time,
            "stage": self._stage,
            "stage_label": self.stage_label(),
            "round_name": rnd_name,
            "queue_name": self._queue.name,
            "queue_id": self._queue.id,
        }

    def next_phase(self) -> config.Phase | None:
        """The phase that will run next (None when this run is finished)."""
        if not self._entry and not self._loop and not self._exit:
            self._build()
        current = self.current_list()
        if 0 <= self._idx + 1 < len(current):
            item = current[self._idx + 1]
            return item[1] if isinstance(item, tuple) else item
        # crossing into the next group
        if self._stage == STAGE_ENTRY:
            if self._loop:
                return self._loop[0][1]
            if self._exit:
                return self._exit[0]
            return None
        if self._stage == STAGE_LOOP:
            if self._will_loop_again():
                return self._loop[0][1] if self._loop else None
            return self._exit[0] if self._exit else None
        return None

    # ------------------------------------------------------------ control ---
    def set_queue(self, queue: config.Queue, autosave: bool = True) -> None:
        self.stop(record=False)
        self._queue = queue
        self.cfg.current_queue = queue.id
        if autosave:
            config.save(self.cfg)

    def start(self) -> None:
        if self._state in (RUNNING, ALERT):
            return
        if self._state == PAUSED:
            self.resume()
            return
        self._build()
        self._pass = 1
        self._until = self._compute_until()
        first = STAGE_ENTRY if self._entry else STAGE_LOOP
        if not self._enter(first):
            self._finish()

    def pause(self) -> None:
        if self._state != RUNNING:
            return
        self._paused_left = max(0.0, self._deadline - time.monotonic())
        self._timer.stop()
        self._pre.stop()
        self._set_state(PAUSED)

    def resume(self) -> None:
        if self._state != PAUSED:
            return
        self._deadline = time.monotonic() + self._paused_left
        self._timer.start()
        self._set_state(RUNNING)
        self._schedule_pre()

    def toggle(self) -> None:
        if self._state == RUNNING:
            self.pause()
        elif self._state == PAUSED:
            self.resume()
        else:
            self.start()

    def skip(self, record: bool = True) -> None:
        """Skip the current phase; it settles as 'skipped' and the queue advances."""
        if self._state == IDLE or self._phase is None:
            return
        self._pre.stop()
        self._timer.stop()
        if record:
            self._settle("skipped", self._elapsed())
        self._advance()

    def stop(self, record: bool = True) -> None:
        if self._state == IDLE:
            return
        self._timer.stop()
        self._pre.stop()
        if record and self._phase is not None:
            self._settle("abandoned", self._elapsed())
        self._phase = None
        self._idx = -1
        self._total = 0.0
        self._stopped = True
        self._set_state(IDLE)
        self.tick.emit(0.0, 0.0)

    def ack(self, action: str = "next") -> None:
        """Acknowledge the alert: next | skip | snooze."""
        if self._state != ALERT or self._phase is None:
            return
        if action == "snooze":
            if not self.can_snooze():
                self._advance()
                return
            self._snoozes += 1
            minutes = max(1, int(self.cfg.settings.snooze_minutes))
            self._total = minutes * 60.0
            self._paused_left = self._total
            self._deadline = time.monotonic() + self._total
            self._pre_done = True
            self._timer.start()
            self._set_state(RUNNING)
            self.phase_changed.emit(self._phase, self.info())
            return
        self._advance()

    # ------------------------------------------------------------ internal ---
    def _build(self) -> None:
        q = self._queue
        self._entry = list(q.entry)
        self._loop = [(rnd.name, ph) for rnd in q.rounds for ph in rnd.phases]
        self._exit = list(q.exit)

    def _compute_until(self) -> datetime | None:
        if self._queue.loop_mode != "until":
            return None
        target = config.parse_hhmm_datetime(self._queue.until_time)
        return target

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _set_stage(self, stage: str) -> None:
        if stage != self._stage:
            self._stage = stage
            self.stage_changed.emit(stage)

    def _elapsed(self) -> float:
        return max(0.0, self._total - self.remaining())

    def _phase_at(self, idx: int) -> config.Phase:
        item = self.current_list()[idx]
        return item[1] if isinstance(item, tuple) else item

    def _enter(self, stage: str) -> bool:
        """Switch to *stage* and start its first phase. False when it is empty."""
        if stage == STAGE_ENTRY and not self._entry:
            return False
        if stage == STAGE_LOOP and not self._loop:
            return False
        if stage == STAGE_EXIT and not self._exit:
            return False
        self._set_stage(stage)
        self._idx = 0
        self._begin()
        return True

    def _begin(self) -> None:
        ph = self._phase_at(self._idx)
        self._phase = ph
        self._total = ph.resolve_seconds()
        self._started_at = time.monotonic()
        self._deadline = self._started_at + self._total
        self._pre_done = False
        self._snoozes = 0
        self._stopped = False
        self._timer.start()
        self._set_state(RUNNING)
        self.phase_changed.emit(ph, self.info())
        hooks.run_all(ph.hooks_start)
        self._schedule_pre()

    def _schedule_pre(self) -> None:
        self._pre.stop()
        ph = self._phase
        if ph is None or not ph.pre_alert or self._pre_done:
            return
        lead_lo = max(5, int(ph.pre_alert_min))
        lead_hi = max(lead_lo, int(ph.pre_alert_max))
        lead = random.uniform(lead_lo, lead_hi)
        left = self.remaining()
        if left <= lead + 5:
            return
        self._pre.start(int((left - lead) * 1000))

    def _on_pre_alert(self) -> None:
        self._pre_done = True
        if self._state == RUNNING and self._phase is not None:
            self.pre_alert.emit(self._phase)

    def _on_tick(self) -> None:
        if self._state != RUNNING:
            return
        left = self._deadline - time.monotonic()
        if left <= 0:
            self._timer.stop()
            self._pre.stop()
            self._settle("completed", self._total)
            self._set_state(ALERT)
            self.alert.emit(self._phase, {**self.info(), "result": "completed"})
            return
        self.tick.emit(left, self._total)

    def _settle(self, result: str, actual: float) -> None:
        ph = self._phase
        if ph is None:
            return
        stats.record_event(
            queue_id=self._queue.id,
            queue_name=self._queue.name,
            phase_id=ph.id,
            phase_name=ph.name,
            kind=ph.kind,
            result=result,
            planned=self._total,
            actual=actual,
        )
        hooks.run_all(ph.hooks_end)

    def _will_loop_again(self) -> bool:
        mode = self._queue.loop_mode
        if mode == "forever":
            return True
        if mode == "until":
            return self._until is not None and datetime.now() < self._until
        count = int(self._queue.loop_count or 0)
        if count <= 0:
            return True
        return self._pass < count

    def _advance(self) -> bool:
        """Move to the next phase; False when the whole queue is finished."""
        current = self.current_list()
        if self._idx + 1 < len(current):
            self._idx += 1
            self._begin()
            return True

        if self._stage == STAGE_ENTRY:
            if self._enter(STAGE_LOOP):
                return True
            if self._enter(STAGE_EXIT):
                return True
            return self._finish()

        if self._stage == STAGE_LOOP:
            if self._will_loop_again() and self._loop:
                self._pass += 1
                self._idx = 0
                self._begin()
                return True
            if self._enter(STAGE_EXIT):
                return True
            return self._finish()

        return self._finish()

    def _finish(self) -> bool:
        self._phase = None
        self._total = 0.0
        self._idx = -1
        self._set_state(IDLE)
        self.tick.emit(0.0, 0.0)
        self.queue_finished.emit()
        return False
