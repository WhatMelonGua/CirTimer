"""Application bootstrap: single instance, wiring, theme switching."""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QCoreApplication, QLockFile, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from pathlib import Path

from . import autostart, config, instance, stats
from . import engine as engine_mod
from . import hooks
from . import theme as theme_mod
from .audio import SOUND_DIR, Audio
from .config import DISPLAY_NAME
from .hotkey import GlobalHotkey, in_dnd, in_schedule
from .presence import PresenceWatcher
from .reminders import SideReminders
from .sitting import SittingTracker
from .ui.alert import AlertWindow
from .ui.hud import HudWindow
from .ui.icons import app_icon
from .ui.main_window import MainWindow
from .ui.tray import Tray

APP_KEY = "CirClock.Desktop"


class App:
    def __init__(self, qt: QApplication) -> None:
        self.qt = qt
        self.cfg = config.load()
        self.theme = theme_mod.load_theme(self.cfg.settings.theme, self.cfg.settings.accent)
        self.audio = Audio()
        self.engine = engine_mod.Engine(self.cfg)
        self.win = MainWindow(self)
        self.alert_win = AlertWindow(self)
        self.hud = HudWindow(self)
        self.tray: Tray | None = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(self)
        else:
            # transiently unavailable (session still starting, Explorer restarted):
            # try once more shortly, otherwise the window simply stays visible
            QTimer.singleShot(2500, self._retry_tray)
        hooks.set_listener(self._on_hook_event)
        self._wire()
        self.apply_theme()

        if self.cfg.settings.autostart != autostart.is_enabled():
            autostart.apply(self.cfg.settings.autostart)

        self.win.show()
        if self.cfg.settings.show_hud:
            self.hud.show()
        if self.cfg.settings.autostart_queue:
            QTimer.singleShot(900, self.engine.start)
        if hooks.is_elevated():
            QTimer.singleShot(1500, self._warn_elevated)

        # -- presence (idle) watching
        self._paused_for_idle = False
        self.presence = PresenceWatcher(self.cfg.settings, None)
        self.presence.away.connect(self._on_away)
        self.presence.back.connect(self._on_back)
        self.presence.start()

        # -- continuous sitting clock
        self._alert_source = "phase"
        self.sitting = SittingTracker(self.cfg.settings, None)
        self.sitting.tick.connect(self.win.timer_page.set_sitting)
        self.sitting.over_limit.connect(self._on_sit_limit)
        self.sitting.start()

        # -- independent water / eye reminders
        self.reminders = SideReminders(self.cfg.settings, None)
        self.reminders.water_due.connect(self._on_water_due)
        self.reminders.eye_due.connect(self._on_eye_due)
        self.reminders.start()

        # -- meeting mode hotkey
        self.meeting = False
        self.cfg.settings.meeting_active = False
        self._meeting_was_running = False
        self.hotkey = GlobalHotkey(self.qt, None)
        self.hotkey.pressed.connect(self.toggle_meeting)
        self._register_hotkey()

        # -- work-hour schedule
        self._sched_active = in_schedule(self.cfg.settings)
        self._sched_started_by_us = False
        self._sched_timer = QTimer()
        self._sched_timer.setInterval(15000)
        self._sched_timer.timeout.connect(self._on_schedule_tick)
        self._sched_timer.start()

        # -- second-instance commands (show / quit); works without a tray icon
        self._cmd_timer = QTimer()
        self._cmd_timer.setInterval(1200)
        self._cmd_timer.timeout.connect(self._poll_command)
        self._cmd_timer.start()

    def _poll_command(self) -> None:
        command = instance.take()
        if command == "show":
            self.show_window()
        elif command == "quit":
            self.quit()

    # ----------------------------------------------------------- hotkeys ---
    def _retry_tray(self) -> None:
        if self.tray is None and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = Tray(self)
            self.tray.refresh()

    def _on_hook_event(self, ok: bool, message: str) -> None:
        if ok:
            return
        if self.tray is not None:
            self.tray.notify("外部动作没执行成功", message)
            return
        if self.win.isVisible():
            self.win.statusBar().showMessage(message, 6000)

    def _warn_elevated(self) -> None:
        text = ("CirClock 正以管理员权限运行：浏览器会提示“已有实例以提升的权限运行”，"
                "记事本这类应用商店程序可能点了没反应。"
                "建议用普通权限启动，或在 设置 → 关于与退出 里点“以普通权限重启”。")
        if self.tray is not None:
            self.tray.notify("以管理员身份运行", text)
        else:
            self.win.statusBar().showMessage(text, 12000)

    def relaunch_unelevated(self) -> None:
        """Relaunch through explorer.exe so the new process gets a normal token."""
        import subprocess

        lock = getattr(self, "_lock", None)
        if lock is not None:
            lock.unlock()
        explorer = Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"
        entry = config.project_root() / "CirClock.pyw"
        try:
            subprocess.Popen([str(explorer), str(entry)], close_fds=True)
        except Exception:
            pass
        self.qt.quit()

    def _register_hotkey(self) -> bool:
        if sys.platform != "win32":
            return False          # global hotkeys are Windows-only for now
        ok = self.hotkey.register(self.cfg.settings.meeting_hotkey)
        if not ok and self.tray is not None:
            self.tray.notify("会议模式快捷键不可用",
                             f"{self.cfg.settings.meeting_hotkey}：{self.hotkey.error}\n"
                             "仍可在托盘菜单里切换。")
        return ok

    def _on_away(self, idle: float) -> None:
        self._paused_for_idle = self.engine.state == engine_mod.RUNNING
        self.sitting.set_present(False)
        if self._paused_for_idle:
            self.engine.pause()
            stats.record_presence("leave", idle)
            if self.tray is not None:
                self.tray.notify("已自动暂停", "检测到你离开了，回来会继续计时。")

    def _on_back(self, duration: float) -> None:
        stats.record_presence("leave_end", duration)
        self.sitting.set_present(True)
        if self._paused_for_idle and not self.meeting:
            self.engine.resume()
        self._paused_for_idle = False

    def _on_sit_limit(self, minutes: float) -> None:
        if self.meeting:
            return
        phase = config.Phase(
            name="坐太久了",
            kind="move",
            color="#E8A33D",
            icon="🧍",
            message=f"已经连续坐了 {minutes:.0f} 分钟。站起来，走两步再回来。",
            actions=["stand_up", "walk", "hip_flexor"],
            require_leave=True,
        )
        self._alert_source = "sitting"
        self.alert_win.present(phase, {"queue_name": "久坐提醒", "index": 1,
                                       "count": 1, "result": "sitting"})
        if self.tray is not None:
            self.tray.notify("久坐提醒", f"已连续坐 {minutes:.0f} 分钟，该起身了。")

    def _on_water_due(self) -> None:
        if self.meeting or in_dnd(self.cfg.settings):
            return
        stats.record_presence("drink", 0.0, "reminder")
        if self.tray is not None:
            self.tray.notify("该喝水了", "接杯水，顺便起来走两步。")
        self.audio.preview(SOUND_DIR / "water_drop.wav", self.cfg.settings.volume)

    def _on_eye_due(self) -> None:
        if self.meeting or in_dnd(self.cfg.settings):
            return
        if self.tray is not None:
            self.tray.notify("20-20-20", "看 6 米外 20 秒，让眼睛歇一下。")
        self.audio.preview(SOUND_DIR / "tick_soft.wav",
                           max(20, self.cfg.settings.volume - 20))

    def toggle_meeting(self) -> None:
        self.meeting = not self.meeting
        self.cfg.settings.meeting_active = self.meeting
        if self.meeting:
            self._meeting_was_running = self.engine.state == engine_mod.RUNNING
            self.engine.pause()
            self.audio.stop()
            if self.alert_win.isVisible():
                self.alert_win.hide()
        elif self._meeting_was_running and not self._paused_for_idle:
            self.engine.resume()
        self.win.refresh_status()
        if self.tray is not None:
            self.tray.notify("会议模式已开启" if self.meeting else "会议模式已关闭",
                             "队列已冻结，时间顺延。" if self.meeting else "队列已恢复。")
            self.tray.refresh()

    # ---------------------------------------------------------- schedule ---
    def _on_schedule_tick(self) -> None:
        active = in_schedule(self.cfg.settings)
        if active and not self._sched_active and self.engine.state == engine_mod.IDLE \
                and not self.meeting:
            self.engine.start()
            self._sched_started_by_us = True
            if self.tray is not None:
                self.tray.notify("进入工作时段", "队列已自动开始。")
        elif not active and self._sched_active and self._sched_started_by_us:
            if self.engine.state in (engine_mod.RUNNING, engine_mod.PAUSED):
                self.engine.stop()
            self._sched_started_by_us = False
            if self.tray is not None:
                self.tray.notify("离开工作时段", "队列已停止并结算。")
        self._sched_active = active

    # -------------------------------------------------------------- wiring ---
    def _wire(self) -> None:
        eng = self.engine
        eng.tick.connect(self._on_tick)
        eng.phase_changed.connect(self._on_phase)
        eng.state_changed.connect(self._on_state)
        eng.alert.connect(self._on_alert)
        eng.pre_alert.connect(self._on_pre_alert)
        eng.queue_finished.connect(self._on_finished)

    def _on_tick(self, remaining: float, total: float) -> None:
        self.win.timer_page.on_tick(remaining, total)
        phase = self.engine.phase
        if phase is not None and self.hud.isVisible():
            from .ui.widgets import format_seconds
            self.hud.update_state(format_seconds(remaining), phase.name,
                                  self.engine.progress(), phase.color)

    def _on_phase(self, phase, info: dict) -> None:
        self.win.timer_page.on_phase(phase, info)
        self.win.refresh_status()
        if self.hud.isVisible():
            from .ui.widgets import format_seconds
            self.hud.update_state(format_seconds(self.engine.remaining()), phase.name,
                                  self.engine.progress(), phase.color)
        if self.tray is not None:
            self.tray.refresh()

    def _on_state(self, state: str) -> None:
        self.win.timer_page.refresh()
        self.win.refresh_status()
        if self.tray is not None:
            self.tray.refresh()
        if state == engine_mod.IDLE and self.hud.isVisible():
            self.hud.update_state("00:00", "未开始", 0.0, self.theme["palette"]["accent"])

    def _on_alert(self, phase, info: dict) -> None:
        self._alert_source = "phase"
        quiet = self.meeting or in_dnd(self.cfg.settings)
        # A corner toast would float exactly on top of the main window's button
        # row, so clicks meant for 停止 would land on the toast instead. When the
        # user is looking at the app, show the card in the middle instead.
        in_app = self.win.isVisible() and self.win.isActiveWindow()
        self.alert_win.present(phase, info, quiet=quiet,
                               force_mode="card" if in_app and not quiet else None)

    def _on_pre_alert(self, phase) -> None:
        if self.meeting or in_dnd(self.cfg.settings):
            return
        if self.tray is not None:
            self.tray.notify("准备一下", f"「{phase.name}」快结束了，起身活动。")
        self.win.timer_page.refresh()

    def _on_finished(self) -> None:
        self.win.timer_page.refresh_stats()
        self.win.stats_page.refresh()
        if self.tray is not None:
            self.tray.notify("队列完成", "这一轮队列跑完了，休息一下或重新开始。")

    # ------------------------------------------------------------ commands ---
    def toggle_timer(self) -> None:
        self.engine.toggle()

    def skip_phase(self) -> None:
        self.alert_win.hide()
        self.audio.stop()
        self.engine.skip()

    def snooze_phase(self) -> None:
        if self.engine.state == engine_mod.ALERT:
            self.alert_win.hide()
            self.audio.stop()
            self.engine.ack("snooze")

    def stop_timer(self) -> None:
        self.alert_win.hide()
        self.audio.stop()
        self.engine.stop()

    def ack_alert(self, action: str) -> None:
        source = getattr(self, "_alert_source", "phase")
        self._alert_source = "phase"
        if source == "sitting":
            if action in ("next", "skip"):
                self.sitting.reset()
                self.win.timer_page.set_sitting(0.0)
            return
        phase = self.engine.phase
        if action == "next" and phase is not None and phase.require_leave:
            stats.record_presence("stand", 0.0, phase.name)
            self.sitting.reset()
            self.win.timer_page.set_sitting(0.0)
        self.engine.ack(action)

    def show_window(self) -> None:
        self.win.show()
        self.win.setWindowState(self.win.windowState() & ~Qt.WindowState.WindowMinimized)
        self.win.raise_()
        self.win.activateWindow()

    def switch_queue(self, queue_id: str) -> None:
        queue = self.cfg.queue_by_id(queue_id)
        if queue is None:
            return
        self.engine.set_queue(queue)
        self.win.timer_page.reload()
        self.win.timer_page.refresh()
        self.win.queue_page.rebuild()
        self.win.refresh_status()

    def replace_queue(self, queue) -> None:
        """Persist an edited queue and rebind the engine if it is the active one."""
        for i, existing in enumerate(self.cfg.queues):
            if existing.id == queue.id:
                self.cfg.queues[i] = queue
                break
        else:
            self.cfg.queues.append(queue)
        self.save()
        if self.engine.queue.id == queue.id:
            if self.engine.state != engine_mod.IDLE:
                self.engine.stop(record=False)
            self.engine.set_queue(queue)
        self.win.timer_page.reload()
        self.win.timer_page.refresh()
        self.win.queue_page.rebuild()
        self.win.refresh_status()

    def switch_theme(self, theme_id: str) -> None:
        if not theme_id or theme_id == self.cfg.settings.theme:
            return
        self.cfg.settings.theme = theme_id
        self.save()
        self.apply_theme()

    def apply_theme(self) -> None:
        self.theme = theme_mod.load_theme(self.cfg.settings.theme, self.cfg.settings.accent)
        self.qt.setStyleSheet(theme_mod.build_qss(self.theme))
        self.win.timer_page.ring.set_theme(self.theme)
        self.win.timer_page.reload()
        self.win.timer_page.refresh()
        self.win.stats_page.chart.set_theme(self.theme)
        self.win.stats_page.refresh()
        self.win.queue_page.rebuild()
        self.alert_win.restyle()
        self.hud.restyle()
        if self.tray is not None:
            self.tray.restyle()
        self.win.setWindowIcon(app_icon())

    def set_muted(self, muted: bool) -> None:
        self.cfg.settings.sound_enabled = not muted
        if muted:
            self.audio.stop()
        self.save()

    def save(self) -> None:
        config.save(self.cfg)

    def cursor_pos(self):
        return QCursor.pos()

    def quit(self) -> None:
        self.save()
        self.audio.stop()
        self.qt.quit()


def _raise_existing_window() -> bool:
    """Bring the already-running CirClock window to the front (Windows).

    Qt titles the window "<window title> - <app name>", so matching the exact
    title fails; match any visible window whose title contains our display name.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = []

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _lparam):
            if found:
                return False
            length = user32.GetWindowTextLengthW(hwnd)
            if length and user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if DISPLAY_NAME in buf.value:
                    found.append(hwnd)
                    return False
            return True

        user32.EnumWindows(enum_proc(callback), 0)
        if not found:
            return False
        hwnd = found[0]
        user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _relaunch_unelevated_once(lock) -> bool:
    """Start a normal-privilege copy through explorer.exe.

    Returns True only when the replacement instance actually took the lock; if
    it never shows up we keep running (an elevated app beats a missing app).
    """
    import subprocess

    marker = config.data_dir() / ".relaunch-guard"
    try:
        if marker.exists():
            age = time.time() - marker.stat().st_mtime
            marker.unlink(missing_ok=True)
            if age < 120:
                return False          # we are the relaunched instance; stay put
        marker.write_text(str(time.time()), encoding="utf-8")
    except OSError:
        return False

    explorer = Path(os.environ.get("WINDIR", r"C:\Windows")) / "explorer.exe"
    entry = config.project_root() / "CirClock.pyw"
    lock.unlock()
    try:
        subprocess.Popen([str(explorer), str(entry)], close_fds=True)
    except Exception:
        lock.lock()
        return False

    # wait for the replacement to claim the single-instance lock
    for _ in range(25):
        time.sleep(0.1)
        if not lock.tryLock(0):
            return True
    lock.lock()          # nobody came: stay alive instead of vanishing
    return False


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv)
    quit_requested = "--quit" in argv
    show_requested = "--show" in argv
    QCoreApplication.setApplicationName("CirClock")
    QCoreApplication.setOrganizationName("CirClock")
    qt = QApplication(argv)
    qt.setApplicationDisplayName("CirClock")
    qt.setQuitOnLastWindowClosed(False)
    qt.setStyle("Fusion")
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_KEY)
    except Exception:
        pass

    # Single instance via a lock file (works even where named pipes are blocked).
    from PySide6.QtCore import QLockFile

    lock = QLockFile(str(config.data_dir() / ".instance.lock"))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(200):
        # another copy owns the lock: ask it to show up or exit, then leave
        instance.send("quit" if quit_requested else "show")
        if not quit_requested:
            _raise_existing_window()
        return 0
    if quit_requested:
        lock.unlock()
        return 0        # nothing was running, nothing to quit

    # An elevated CirClock hands its token to every child: browsers complain and
    # packaged apps refuse to start. Prefer running unelevated, once.
    if hooks.is_elevated() and "--keep-elevated" not in argv:
        if _relaunch_unelevated_once(lock):
            return 0

    app = App(qt)
    app._lock = lock
    qt.aboutToQuit.connect(app.save)
    try:
        return qt.exec()
    finally:
        lock.unlock()
