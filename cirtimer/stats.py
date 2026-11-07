"""SQLite event log: settled phases, breaks, standing confirmations, CSV export."""
from __future__ import annotations

import csv
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import data_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    day TEXT NOT NULL,
    queue_id TEXT,
    queue_name TEXT,
    phase_id TEXT,
    phase_name TEXT,
    kind TEXT,
    result TEXT,          -- completed | skipped | snoozed | abandoned
    planned REAL,         -- seconds the phase was supposed to take
    actual REAL           -- seconds actually spent
);
CREATE TABLE IF NOT EXISTS presence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    day TEXT NOT NULL,
    kind TEXT,            -- stand | sit | drink | leave
    seconds REAL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_day ON events(day);
"""


def db_path() -> Path:
    return data_dir() / "history.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), timeout=5)
    conn.executescript(SCHEMA)
    return conn


def _day(ts: float | None = None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else time.time()).strftime("%Y-%m-%d")


def record_event(queue_id: str, queue_name: str, phase_id: str, phase_name: str,
                 kind: str, result: str, planned: float, actual: float,
                 ts: float | None = None) -> None:
    ts = ts if ts is not None else time.time()
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO events (ts, day, queue_id, queue_name, phase_id, phase_name,"
                " kind, result, planned, actual) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, _day(ts), queue_id, queue_name, phase_id, phase_name, kind, result,
                 planned, actual),
            )
    except sqlite3.Error:
        # statistics must never break the timer
        pass


def record_presence(kind: str, seconds: float = 0.0, note: str = "",
                    ts: float | None = None) -> None:
    ts = ts if ts is not None else time.time()
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO presence (ts, day, kind, seconds, note) VALUES (?,?,?,?,?)",
                (ts, _day(ts), kind, seconds, note))
    except sqlite3.Error:
        pass


def today_summary() -> dict:
    day = _day()
    out = {
        "focus_minutes": 0.0,
        "breaks": 0,
        "skips": 0,
        "completed": 0,
        "stands": 0,
        "drinks": 0,
        "longest_sit": 0.0,
    }
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT kind, result, actual FROM events WHERE day = ?", (day,)).fetchall()
            for kind, result, actual in rows:
                if result == "completed":
                    out["completed"] += 1
                    if kind == "focus":
                        out["focus_minutes"] += (actual or 0) / 60.0
                    else:
                        out["breaks"] += 1
                elif result == "skipped":
                    out["skips"] += 1
            out["stands"] = conn.execute(
                "SELECT COUNT(*) FROM presence WHERE day = ? AND kind = 'stand'",
                (day,)).fetchone()[0]
            out["drinks"] = conn.execute(
                "SELECT COUNT(*) FROM presence WHERE day = ? AND kind = 'drink'",
                (day,)).fetchone()[0]
            row = conn.execute(
                "SELECT MAX(seconds) FROM presence WHERE day = ? AND kind = 'sit'",
                (day,)).fetchone()
            out["longest_sit"] = float(row[0] or 0.0) / 60.0
    except sqlite3.Error:
        pass
    return out


def week_series(days: int = 7) -> list[dict]:
    """Per-day totals for the last N days (oldest first)."""
    out = []
    today = datetime.now().date()
    with _conn() as conn:
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            key = d.strftime("%Y-%m-%d")
            row = conn.execute(
                "SELECT COALESCE(SUM(CASE WHEN kind='focus' AND result='completed'"
                " THEN actual ELSE 0 END),0),"
                " COALESCE(SUM(CASE WHEN kind!='focus' AND result='completed' THEN 1 ELSE 0 END),0)"
                " FROM events WHERE day = ?", (key,)).fetchone()
            out.append({"day": key, "focus_minutes": (row[0] or 0) / 60.0,
                        "breaks": row[1] or 0})
    return out


CSV_HEADER = ["时间", "队列", "阶段", "类型", "结果", "计划秒", "实际秒"]


def export_csv(path: str | Path) -> int:
    rows = []
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ts, queue_name, phase_name, kind, result, planned, actual"
            " FROM events ORDER BY ts").fetchall()
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADER)
        for ts, qn, pn, kind, result, planned, actual in rows:
            w.writerow([datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                        qn, pn, kind, result, f"{planned:.1f}", f"{actual:.1f}"])
    return len(rows)
