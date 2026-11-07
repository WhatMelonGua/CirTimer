"""System tray icon + context menu."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import engine as engine_mod
from ..config import DISPLAY_NAME
from .icons import app_icon


class Tray(QSystemTrayIcon):
    def __init__(self, app) -> None:
        super().__init__(app_icon(), None)
        self.app = app
        self.setToolTip(DISPLAY_NAME)
        self.menu = QMenu()
        self.act_show = QAction("显示主窗口", self.menu)
        self.act_toggle = QAction("开始", self.menu)
        self.act_skip = QAction("跳过本段", self.menu)
        self.act_mute = QAction("静音", self.menu)
        self.act_mute.setCheckable(True)
        self.act_mute.setChecked(not app.cfg.settings.sound_enabled)
        self.act_quit = QAction("退出", self.menu)
        self.menu.addAction(self.act_show)
        self.menu.addSeparator()
        self.menu.addAction(self.act_toggle)
        self.menu.addAction(self.act_skip)
        self.menu.addSeparator()
        self.menu.addAction(self.act_mute)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)
        self.setContextMenu(self.menu)

        self.act_show.triggered.connect(app.show_window)
        self.act_toggle.triggered.connect(app.toggle_timer)
        self.act_skip.triggered.connect(app.skip_phase)
        self.act_mute.toggled.connect(app.set_muted)
        self.act_quit.triggered.connect(app.quit)

        self.activated.connect(self._on_activated)
        self.refresh()
        self.show()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.app.show_window()

    def refresh(self) -> None:
        eng = self.app.engine
        state = eng.state
        if state == engine_mod.RUNNING:
            self.act_toggle.setText("暂停")
        elif state == engine_mod.PAUSED:
            self.act_toggle.setText("继续")
        else:
            self.act_toggle.setText("开始")
        self.act_skip.setEnabled(state in (engine_mod.RUNNING, engine_mod.PAUSED,
                                           engine_mod.ALERT))
        color = self.app.theme["palette"]["accent"]
        if eng.phase is not None:
            color = eng.phase.color
        self.setIcon(app_icon())
        phase = eng.phase
        if phase is not None:
            left = int(eng.remaining())
            self.setToolTip(f"{DISPLAY_NAME} · {phase.name} · 剩 {left // 60} 分 {left % 60} 秒")
        else:
            self.setToolTip(f"{DISPLAY_NAME} · 未开始")

    def restyle(self) -> None:
        self.refresh()

    def notify(self, title: str, message: str) -> None:
        try:
            self.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)
        except Exception:
            pass
