"""Configuration model + JSON persistence for CirClock."""
from __future__ import annotations

import json
import os
import sys
import random
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any

APP_NAME = "CirClock"
DISPLAY_NAME = "超能苹果钟"        # shown in the window title, tray and about box
SCHEMA_VERSION = 1
CONFIG_FILE = "config.json"


# ------------------------------------------------------------------ paths ---
def is_frozen() -> bool:
    """True when running from a PyInstaller bundle."""
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Where themes/ and assets/ live: the repo root, or the bundle root."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def data_dir() -> Path:
    """Where config/history live.

    Priority: ``CIRCLOCK_DATA`` env var -> (frozen) ``data`` next to the exe ->
    ``portable.marker`` in the project -> ``%APPDATA%/CirClock`` -> ``<project>/data``.
    """
    override = os.environ.get("CIRCLOCK_DATA")
    if override:
        d = Path(override)
        d.mkdir(parents=True, exist_ok=True)
        return d

    root = project_root()
    if is_frozen():
        candidates = [Path(sys.executable).parent / "data"]
    else:
        local = root / "data"
        if (root / "portable.marker").exists():
            candidates = [local]
        else:
            appdata = os.environ.get("APPDATA")
            candidates = [Path(appdata) / APP_NAME] if appdata else []
            candidates.append(local)

    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return d
        except OSError:
            continue
    raise RuntimeError("no writable data directory")


def config_path() -> Path:
    return data_dir() / CONFIG_FILE


# ----------------------------------------------------------------- models ---
@dataclass
class Hook:
    """External action fired when a phase starts or ends."""

    type: str = "open"          # open (shell association: URL or file) | run (executable)
    target: str = ""
    program: str = ""           # optional: open with this exe instead of the default app
    args: str = ""
    cwd: str = ""
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Hook":
        data = data or {}
        return cls(
            type=str(data.get("type", "open")),
            target=str(data.get("target", "")),
            program=str(data.get("program", "")),
            args=str(data.get("args", "")),
            cwd=str(data.get("cwd", "")),
            enabled=bool(data.get("enabled", True)),
        )


PHASE_KINDS = ("focus", "break", "move", "stretch", "eye", "water", "custom")


@dataclass
class Phase:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "专注"
    kind: str = "focus"
    minutes: float = 25.0
    use_range: bool = False
    minutes_min: float = 20.0
    minutes_max: float = 30.0

    color: str = "#2B6CF6"
    icon: str = ""                 # emoji / built-in svg id / absolute image path
    sticker: str = ""              # optional decoration shown on the alert card
    sound: str = ""                # see audio.resolve_sound(); empty = phase default
    message: str = ""              # text shown by the alert
    actions: list[str] = field(default_factory=list)   # action-library ids

    require_leave: bool = False    # must confirm standing up
    allow_skip: bool = True
    pre_alert: bool = True
    pre_alert_min: int = 30
    pre_alert_max: int = 90

    hooks_start: list[Hook] = field(default_factory=list)
    hooks_end: list[Hook] = field(default_factory=list)

    # -- behaviour
    def resolve_seconds(self) -> float:
        if self.use_range and self.minutes_max > 0:
            lo, hi = sorted((float(self.minutes_min), float(self.minutes_max)))
            return max(5.0, random.uniform(lo, hi) * 60.0)
        return max(5.0, float(self.minutes) * 60.0)

    # -- serialisation
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["hooks_start"] = [h.to_dict() for h in self.hooks_start]
        d["hooks_end"] = [h.to_dict() for h in self.hooks_end]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Phase":
        names = {f.name for f in fields(cls)} - {"hooks_start", "hooks_end"}
        kw = {k: v for k, v in (data or {}).items() if k in names}
        kw["hooks_start"] = [Hook.from_dict(h) for h in (data or {}).get("hooks_start", [])]
        kw["hooks_end"] = [Hook.from_dict(h) for h in (data or {}).get("hooks_end", [])]
        kw.setdefault("actions", [])
        return cls(**kw)


@dataclass
class Round:
    name: str = "第 1 轮"
    phases: list[Phase] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "phases": [p.to_dict() for p in self.phases]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Round":
        return cls(
            name=str((data or {}).get("name", "轮次")),
            phases=[Phase.from_dict(p) for p in (data or {}).get("phases", [])],
        )


@dataclass
class Queue:
    id: str = field(default_factory=lambda: "q_" + uuid.uuid4().hex[:6])
    name: str = "新队列"
    rounds: list[Round] = field(default_factory=list)
    loop_count: int = 1            # used when loop_mode == "count"; 0 = forever
    loop_mode: str = "count"       # count | forever | until
    until_time: str = "18:30"      # used when loop_mode == "until"
    entry: list[Phase] = field(default_factory=list)   # 起始阶段
    exit: list[Phase] = field(default_factory=list)    # 结束阶段
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "loop_count": self.loop_count,
            "loop_mode": self.loop_mode,
            "until_time": self.until_time,
            "description": self.description,
            "entry": [p.to_dict() for p in self.entry],
            "exit": [p.to_dict() for p in self.exit],
            "rounds": [r.to_dict() for r in self.rounds],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Queue":
        loop_count = int(data.get("loop_count", 1))
        mode = str(data.get("loop_mode", "") or "")
        if mode not in ("count", "forever", "until"):
            mode = "forever" if loop_count == 0 else "count"
        return cls(
            id=str(data.get("id") or "q_" + uuid.uuid4().hex[:6]),
            name=str(data.get("name", "队列")),
            loop_count=loop_count,
            loop_mode=mode,
            until_time=str(data.get("until_time", "18:30")),
            description=str(data.get("description", "")),
            entry=[Phase.from_dict(p) for p in data.get("entry", [])],
            exit=[Phase.from_dict(p) for p in data.get("exit", [])],
            rounds=[Round.from_dict(r) for r in data.get("rounds", [])],
        )

    # -- helpers
    def phase_count(self) -> int:
        """Phases in one loop pass."""
        return sum(len(r.phases) for r in self.rounds)

    def total_phases(self) -> int:
        return len(self.entry) + self.phase_count() + len(self.exit)

    def loop_label(self) -> str:
        if self.loop_mode == "forever":
            return "无限循环"
        if self.loop_mode == "until":
            return f"循环到 {self.until_time}"
        return f"循环 {self.loop_count or 1} 轮"

    def total_seconds(self) -> float:
        return sum(p.minutes * 60 for r in self.rounds for p in r.phases)


@dataclass
class Settings:
    # appearance
    theme: str = "fluent-light"
    accent: str = ""                 # optional accent override (hex)
    density: str = "comfortable"     # comfortable | compact
    # behaviour on launch
    autostart: bool = False          # register in HKCU Run
    autostart_queue: bool = False    # start the default queue immediately
    default_queue: str = ""
    # alerts
    sound_enabled: bool = True
    volume: int = 60                 # 0..100
    topmost: bool = True
    steal_focus: bool = False
    progressive: bool = True
    toast_seconds: int = 20          # escalate to full screen after this
    fullscreen: bool = False         # directly full screen
    snooze_minutes: int = 5
    snooze_limit: int = 2
    # presence
    idle_seconds: int = 180
    auto_pause_on_idle: bool = True
    sitting_limit_minutes: int = 50
    break_confirm: bool = True
    water_enabled: bool = True
    water_interval_minutes: int = 60
    eye_enabled: bool = False
    # schedule / meeting
    schedule_enabled: bool = False
    schedule_days: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5])
    schedule_windows: list[list[str]] = field(
        default_factory=lambda: [["09:00", "12:00"], ["13:30", "18:30"]])
    meeting_active: bool = False
    dnd_enabled: bool = False
    quiet_in_dnd: bool = True
    # windows
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    show_hud: bool = True
    hud_pos: list[int] = field(default_factory=lambda: [-1, -1])
    meeting_hotkey: str = "Ctrl+Alt+M"
    dnd_ranges: list[list[str]] = field(default_factory=list)   # [["12:00","13:30"]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        names = {f.name for f in fields(cls)}
        kw = {k: v for k, v in (data or {}).items() if k in names}
        return cls(**kw)


@dataclass
class Config:
    version: int = SCHEMA_VERSION
    settings: Settings = field(default_factory=Settings)
    queues: list[Queue] = field(default_factory=list)
    current_queue: str = ""

    # -- access
    def queue_by_id(self, qid: str) -> Queue | None:
        for q in self.queues:
            if q.id == qid:
                return q
        return None

    def current(self) -> Queue:
        q = self.queue_by_id(self.current_queue or self.settings.default_queue)
        if q is None and self.queues:
            q = self.queues[0]
            self.current_queue = q.id
        if q is None:
            q = default_queues()[0]
            self.queues.append(q)
            self.current_queue = q.id
        return q

    # -- persistence
    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "settings": self.settings.to_dict(),
            "current_queue": self.current_queue,
            "queues": [q.to_dict() for q in self.queues],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        queues = [Queue.from_dict(q) for q in data.get("queues", [])]
        cfg = cls(
            version=int(data.get("version", SCHEMA_VERSION)),
            settings=Settings.from_dict(data.get("settings", {})),
            queues=queues,
            current_queue=str(data.get("current_queue", "")),
        )
        if not cfg.queues:
            cfg.queues = default_queues()
        if not cfg.current_queue or cfg.queue_by_id(cfg.current_queue) is None:
            cfg.current_queue = cfg.queues[0].id
        if not cfg.settings.default_queue or cfg.queue_by_id(cfg.settings.default_queue) is None:
            cfg.settings.default_queue = cfg.current_queue
        return cfg


# ---------------------------------------------------------------- presets ---
def _phase(name: str, kind: str, minutes: float, color: str, icon: str = "",
           message: str = "", **kw: Any) -> Phase:
    p = Phase(name=name, kind=kind, minutes=minutes, color=color, icon=icon, message=message)
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def default_queues() -> list[Queue]:
    sit = Queue(
        id="q_sit",
        name="久坐保健",
        loop_count=3,
        description="50 分钟专注 + 5 分钟离座，第二轮后做膝髋拉伸。",
        rounds=[
            Round(name="第 1 轮", phases=[
                _phase("专注工作", "focus", 50, "#2B6CF6", "🧑‍💻", "坐直，肩放松，屏幕与视线平齐。"),
                _phase("离座活动", "move", 5, "#12B886", "🚶", "站起来走一圈，顺便补水。",
                       require_leave=True, actions=["walk"]),
            ]),
            Round(name="第 2 轮", phases=[
                _phase("专注工作", "focus", 50, "#2B6CF6", "🧑‍💻", "坐直，肩放松，屏幕与视线平齐。"),
                _phase("膝髋拉伸", "stretch", 8, "#E8A33D", "🧘", "靠墙静蹲、髋屈肌拉伸、腘绳肌拉伸。",
                       require_leave=True, actions=["wall_squat", "hip_flexor", "hamstring"]),
            ]),
        ],
    )
    pomo = Queue(
        id="q_pomo",
        name="经典番茄",
        loop_count=1,
        description="25/5 × 4，第 4 轮后长休息 15 分钟。",
        rounds=[
            Round(name="番茄 1", phases=[
                _phase("专注", "focus", 25, "#2B6CF6", "🍅", "只做一件事。"),
                _phase("短休息", "break", 5, "#12B886", "☕", "离开屏幕，看看远处。"),
            ]),
            Round(name="番茄 2", phases=[
                _phase("专注", "focus", 25, "#2B6CF6", "🍅", "只做一件事。"),
                _phase("短休息", "break", 5, "#12B886", "☕", "离开屏幕，看看远处。"),
            ]),
            Round(name="番茄 3", phases=[
                _phase("专注", "focus", 25, "#2B6CF6", "🍅", "只做一件事。"),
                _phase("短休息", "break", 5, "#12B886", "☕", "离开屏幕，看看远处。"),
            ]),
            Round(name="番茄 4", phases=[
                _phase("专注", "focus", 25, "#2B6CF6", "🍅", "只做一件事。"),
                _phase("长休息", "break", 15, "#7C6CF6", "🛋", "彻底离开工位，走动一下。",
                       require_leave=True),
            ]),
        ],
    )
    knee = Queue(
        id="q_knee",
        name="膝髋养护",
        loop_count=3,
        description="40 分钟专注后做 3 分钟微运动，交替拉伸。",
        rounds=[
            Round(name="第 1 轮", phases=[
                _phase("专注工作", "focus", 40, "#2B6CF6", "🧑‍💻", "每 15 分钟挪一次坐姿。"),
                _phase("微运动", "move", 3, "#12B886", "🦵", "坐姿伸膝 10 次 ×2，直腿抬高 10 次。",
                       actions=["seated_ext", "leg_raise"]),
            ]),
            Round(name="第 2 轮", phases=[
                _phase("专注工作", "focus", 40, "#2B6CF6", "🧑‍💻", "每 15 分钟挪一次坐姿。"),
                _phase("拉伸", "stretch", 6, "#E8A33D", "🧘", "髋屈肌 + 腘绳肌 + 小腿，各 40 秒。",
                       require_leave=True, actions=["hip_flexor", "hamstring", "calf"]),
            ]),
        ],
    )
    pelvis = Queue(
        id="q_pelvis",
        name="盆腔友好",
        loop_count=3,
        description="45 分钟专注后起身走动，配合提肛与腹式呼吸。",
        rounds=[
            Round(name="第 1 轮", phases=[
                _phase("专注工作", "focus", 45, "#2B6CF6", "🧑‍💻", "坐骨坐实，别塌腰。"),
                _phase("起身走动", "move", 3, "#12B886", "🚶", "走动 + 提肛 10 次 ×3 组。",
                       require_leave=True, actions=["walk", "kegel"]),
            ]),
            Round(name="第 2 轮", phases=[
                _phase("专注工作", "focus", 45, "#2B6CF6", "🧑‍💻", "坐骨坐实，别塌腰。"),
                _phase("呼吸放松", "break", 5, "#7C6CF6", "🌿", "腹式呼吸 2 分钟 + 髋屈肌拉伸。",
                       actions=["breathing", "hip_flexor"]),
            ]),
        ],
    )
    care = Queue(
        id="q_care",
        name="护眼补水",
        loop_count=2,
        description="45 分钟专注后远眺 + 补水，眼和腰同时照顾。",
        rounds=[
            Round(name="第 1 轮", phases=[
                _phase("专注工作", "focus", 45, "#2B6CF6", "🧑‍💻", "屏幕略低于视线，肩放松。"),
                _phase("远眺放松", "eye", 1, "#7C6CF6", "👁",
                       "看 6 米外 20 秒，再眨眨眼，顺便喝水。", actions=["eye_2020"]),
            ]),
            Round(name="第 2 轮", phases=[
                _phase("专注工作", "focus", 45, "#2B6CF6", "🧑‍💻", "屏幕略低于视线，肩放松。"),
                _phase("补水走动", "water", 3, "#1FA8C9", "💧",
                       "接一杯水，回来前绕一圈。", require_leave=True, actions=["walk"]),
            ]),
        ],
    )
    day = Queue(
        id="q_day",
        name="日常卡点",
        loop_mode="until",
        until_time="18:30",
        description="一直做工位节律，到 18:30 自动收工。",
        entry=[
            _phase("开工准备", "custom", 3, "#7C6CF6", "🌅",
                   "列一下今天最重要的三件事。"),
        ],
        exit=[
            _phase("收工复盘", "custom", 5, "#7C6CF6", "🌙",
                   "保存工作，写下明天第一件事。"),
        ],
        rounds=[
            Round(name="工位节律", phases=[
                _phase("专注工作", "focus", 45, "#2B6CF6", "🧑‍💻", "只做当前这一件事。"),
                _phase("起身活动", "move", 5, "#12B886", "🚶", "离开椅子走一圈。",
                       require_leave=True, actions=["walk", "hip_flexor"]),
            ]),
        ],
    )
    return [sit, pomo, knee, pelvis, care, day]


# ------------------------------------------------------------------- I/O ---
def parse_hhmm(text: str) -> dtime | None:
    try:
        hh, mm = str(text).strip().split(":")
        return dtime(int(hh), int(mm))
    except Exception:
        return None


def parse_hhmm_datetime(text: str, now: datetime | None = None) -> datetime | None:
    """Today's HH:MM (may already be in the past), or None when unparseable."""
    clock = parse_hhmm(text)
    if clock is None:
        return None
    base = now or datetime.now()
    return base.replace(hour=clock.hour, minute=clock.minute, second=0, microsecond=0)


def load() -> Config:
    path = config_path()
    if not path.exists():
        cfg = Config(queues=default_queues(), current_queue="q_sit")
        cfg.settings.default_queue = "q_sit"
        save(cfg)
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        backup = path.with_suffix(".broken.json")
        try:
            path.replace(backup)
        except OSError:
            pass
        cfg = Config(queues=default_queues(), current_queue="q_sit")
        cfg.settings.default_queue = "q_sit"
        return cfg
    return Config.from_dict(data)


def save(cfg: Config) -> None:
    path = config_path()
    tmp = path.with_suffix(".tmp")
    payload = json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2)
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
