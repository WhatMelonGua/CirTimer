"""Main window: sidebar navigation + stacked pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..config import DISPLAY_NAME
from .icons import app_icon, brand_pixmap
from .pages import QueuePage, SettingsPage, StatsPage, TimerPage


class MainWindow(QMainWindow):
    def __init__(self, app) -> None:
        super().__init__()
        self.app = app
        self.setWindowTitle(DISPLAY_NAME)
        self.resize(1024, 700)
        self.setMinimumSize(900, 620)
        self.setWindowIcon(app_icon())

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # pages first: nav buttons need the stack
        self.stack = QStackedWidget()
        self.timer_page = TimerPage(app)
        self.queue_page = QueuePage(app)
        self.stats_page = StatsPage(app)
        self.settings_page = SettingsPage(app)
        for page in (self.timer_page, self.queue_page, self.stats_page, self.settings_page):
            self.stack.addWidget(page)

        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(200)
        v = QVBoxLayout(sidebar)
        v.setContentsMargins(12, 16, 12, 14)
        v.setSpacing(3)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(brand_pixmap(26))
        logo.setFixedWidth(28)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel(DISPLAY_NAME)
        brand.setObjectName("Brand")
        brand_sub = QLabel("自由循环 · 工位节律")
        brand_sub.setObjectName("BrandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(brand_sub)
        brand_row.addWidget(logo)
        brand_row.addLayout(brand_col, 1)
        v.addLayout(brand_row)
        v.addSpacing(16)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, text in enumerate(("计时", "队列", "统计", "设置")):
            btn = QPushButton(text)
            btn.setObjectName("Nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=index: self.stack.setCurrentIndex(i))
            v.addWidget(btn)
            self.nav_group.addButton(btn, index)
            self.nav_buttons.append(btn)
        self.nav_buttons[0].setChecked(True)

        v.addStretch()
        self.status = QLabel("未开始")
        self.status.setObjectName("Faint")
        self.status.setWordWrap(True)
        v.addWidget(self.status)

        # always-visible exit: the settings page one is easy to miss
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {app.theme['palette']['border']};")
        v.addSpacing(6)
        v.addWidget(line)
        self.quit_btn = QPushButton("退出程序")
        self.quit_btn.setObjectName("QuitLink")
        self.quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quit_btn.setToolTip("结束进程，后台计时也会停止（Ctrl+Q）")
        self.quit_btn.clicked.connect(app.quit)
        v.addWidget(self.quit_btn)

        h.addWidget(sidebar)
        h.addWidget(self.stack, 1)

        # Ctrl+Q quits from anywhere in the window
        shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        shortcut.activated.connect(app.quit)
        self.refresh_status()

    # ------------------------------------------------------------------ ui ---
    def refresh_status(self) -> None:
        from .. import engine as engine_mod

        eng = self.app.engine
        queue = eng.queue
        loops = "∞" if queue.loop_count == 0 else str(queue.loop_count)
        state = eng.state
        if state == engine_mod.RUNNING and eng.phase is not None:
            text = f"进行中 · {eng.phase.name}\n{queue.name} · 循环 {loops} 轮"
        elif state == engine_mod.PAUSED:
            text = "已暂停"
        elif state == engine_mod.ALERT:
            text = "等待结算"
        else:
            text = f"未开始 · {queue.name}"
        self.status.setText(text)

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.nav_buttons[index].setChecked(True)

    # --------------------------------------------------------------- close ---
    def closeEvent(self, event) -> None:  # noqa: N802
        # Never hide into a tray that does not exist — that would leave a
        # window-less process with no way to get back.
        if self.app.cfg.settings.close_to_tray and self.app.tray is not None:
            event.ignore()
            self.hide()
            if self.app.tray is not None:
                self.app.tray.notify("CirClock 仍在后台运行",
                                     "双击托盘图标回来；要退出：右键托盘 → 退出，"
                                     "或运行项目里的「退出.cmd」。")
        else:
            event.accept()
            self.app.quit()
