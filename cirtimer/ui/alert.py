"""Progressive alert window: corner toast -> centred card -> full screen.

The widget tree is built once and then updated in place; rebuilding a dynamic
layout on every alert leaves deferred-deleted widgets on screen until the event
loop runs, which shows up as duplicated button rows.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

from .. import actions as actions_mod
from .. import audio as audio_mod
from .icons import svg_pixmap


class AlertWindow(QWidget):
    """One window, three sizes. Never stacks: a new alert replaces the old one."""

    def __init__(self, app) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._mode = "toast"
        self._phase = None
        self._info: dict = {}

        self._card = QFrame(self)
        self._card.setObjectName("AlertCard")
        body = QVBoxLayout(self._card)
        body.setContentsMargins(20, 16, 20, 16)
        body.setSpacing(6)

        self._strip = QFrame()
        self._strip.setFixedHeight(4)
        body.addWidget(self._strip)

        head = QHBoxLayout()
        head.setSpacing(10)
        self._icon = QLabel("⏰")
        self._icon.setFixedWidth(34)
        head.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(1)
        self._title = QLabel("")
        self._sub = QLabel("")
        col.addWidget(self._title)
        col.addWidget(self._sub)
        head.addLayout(col, 1)
        body.addLayout(head)

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        body.addWidget(self._msg)

        # action rows: a fixed pool, filled/hidden per alert (no rebuilding)
        self._action_rows: list[dict] = []
        self._actions_box = QWidget()
        ab = QVBoxLayout(self._actions_box)
        ab.setContentsMargins(0, 4, 0, 0)
        ab.setSpacing(6)
        for _ in range(4):
            row = QWidget()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            icon = QLabel()
            icon.setFixedSize(40, 40)
            text_col = QVBoxLayout()
            text_col.setSpacing(0)
            name = QLabel("")
            detail = QLabel("")
            detail.setWordWrap(True)
            text_col.addWidget(name)
            text_col.addWidget(detail)
            lay.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            lay.addLayout(text_col, 1)
            ab.addWidget(row)
            self._action_rows.append({"row": row, "icon": icon, "name": name,
                                      "detail": detail})
            row.hide()
        self._actions_box.hide()
        body.addWidget(self._actions_box)

        body.addStretch()

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self._ok = QPushButton("完成")
        self._ok.setObjectName("AlertPrimary")
        self._ok.clicked.connect(lambda: self._ack("next"))
        self._snz = QPushButton("推迟")
        self._snz.setObjectName("AlertGhost")
        self._snz.clicked.connect(lambda: self._ack("snooze"))
        self._skip = QPushButton("跳过")
        self._skip.setObjectName("AlertGhost")
        self._skip.clicked.connect(lambda: self._ack("skip"))
        for b in (self._ok, self._snz, self._skip):
            btns.addWidget(b)
        btns.addStretch()
        body.addLayout(btns)

        self._esc = QTimer(self)
        self._esc.setSingleShot(True)
        self._esc.timeout.connect(self._escalate)

        self._apply_style()

    # ----------------------------------------------------------- styling ---
    def _apply_style(self) -> None:
        pal = self.app.theme["palette"]
        self._card.setStyleSheet(f"""
            #AlertCard {{
                background: {pal['surface']};
                border: 1px solid {pal['border']};
                border-radius: 12px;
            }}
            QLabel {{ background: transparent; color: {pal['text']}; }}
            QPushButton#AlertGhost {{
                background: transparent; color: {pal['text']};
                border: 1px solid {pal['border_strong']};
                border-radius: 16px; padding: 7px 16px;
            }}
            QPushButton#AlertGhost:hover {{ background: {pal['surface_alt']}; }}
            QPushButton#AlertPrimary {{
                background: {pal['accent']}; color: {pal['accent_text']};
                border: 1px solid {pal['accent']};
                border-radius: 16px; padding: 7px 20px; font-weight: 600;
            }}
        """)
        self._title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self._sub.setStyleSheet(f"color: {pal['text_sub']}; font-size: 11px;")
        self._msg.setStyleSheet(f"color: {pal['text_sub']}; font-size: 12px;")
        self._icon.setStyleSheet("font-size: 26px;")

    def restyle(self) -> None:
        self._apply_style()
        self.update()

    # ------------------------------------------------------------- show ----
    def present(self, phase, info: dict, quiet: bool = False,
                force_mode: str | None = None) -> None:
        self._phase = phase
        self._info = info or {}
        settings = self.app.cfg.settings

        self._apply_style()
        self._strip.setStyleSheet(f"background: {phase.color}; border-radius: 2px;")
        self._icon.setText(phase.icon or ("⏰" if phase.kind == "focus" else "🧘"))
        self._title.setText(phase.name)
        self._sub.setText(f"{self._info.get('queue_name', '')} · 第 "
                          f"{self._info.get('index', 0)} 段 / 共 {self._info.get('count', 0)} 段")
        default_msg = ("时间到，起来活动一下。" if phase.kind != "focus"
                       else "这一段结束了，结算一下。")
        self._msg.setText(phase.message or default_msg)

        acts = actions_mod.resolve(phase.actions)
        self._fill_actions(acts)
        extra = min(4, len(acts)) * 50 if acts else 0

        can_snooze = self.app.engine.can_snooze()
        self._snz.setVisible(can_snooze)
        self._snz.setText(f"推迟 {settings.snooze_minutes} 分钟")
        self._ok.setText("完成" if phase.kind == "focus" else "我已完成")

        if force_mode:
            mode = force_mode
        elif quiet or settings.fullscreen:
            mode = "full" if settings.fullscreen and not quiet else "card"
        elif settings.progressive:
            mode = "toast"
        else:
            mode = "card"
        self._place(mode, extra)

        self.show()
        if not quiet:
            self.raise_()
            if settings.steal_focus:
                self.activateWindow()

        self.app.audio.stop()
        if not quiet:
            self.app.audio.play(audio_mod.resolve_sound(phase, settings), settings.volume)

        if mode == "toast" and settings.progressive:
            self._esc.start(max(5, int(settings.toast_seconds)) * 1000)

    def _escalate(self) -> None:
        if not self.isVisible():
            return
        settings = self.app.cfg.settings
        if settings.fullscreen:
            self._place("full")
        elif self._mode == "toast":
            self._place("card")
            self.raise_()
            if settings.steal_focus:
                self.activateWindow()

    def _place(self, mode: str, extra: int = 0) -> None:
        self._mode = mode
        screen = QGuiApplication.screenAt(self.app.cursor_pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()

        if mode == "toast":
            w, h = 400, 190 + extra
            self._card.setGeometry(0, 0, w, h)
            self.setGeometry(geo.right() - w - 24, geo.bottom() - h - 24, w, h)
        elif mode == "card":
            self.setGeometry(geo)
            w, h = 540, 300 + extra
            self._card.setGeometry((geo.width() - w) // 2, (geo.height() - h) // 2, w, h)
        else:  # full
            self.setGeometry(geo)
            w, h = 640, 360 + extra
            self._card.setGeometry((geo.width() - w) // 2, (geo.height() - h) // 2, w, h)
        self.update()

    def _fill_actions(self, acts) -> None:
        if not acts:
            self._actions_box.hide()
            return
        pal = self.app.theme["palette"]
        for i, slot in enumerate(self._action_rows):
            if i >= len(acts):
                slot["row"].hide()
                continue
            action = acts[i]
            slot["icon"].setPixmap(svg_pixmap(action.svg, 40, pal["text_sub"]))
            if action.seconds >= 60:
                amount = f"{action.seconds / 60:g} 分钟"
            else:
                amount = f"{action.seconds} 秒"
            slot["name"].setText(f"{action.name} · {amount}")
            slot["name"].setStyleSheet(f"font-size: 12px; font-weight: 600; color: {pal['text']};")
            slot["detail"].setText(action.detail)
            slot["detail"].setStyleSheet(f"color: {pal['text_sub']}; font-size: 11px;")
            slot["row"].show()
        self._actions_box.show()

    # -------------------------------------------------------------- paint ---
    def paintEvent(self, event) -> None:  # noqa: N802
        if self._mode == "toast":
            return
        p = QPainter(self)
        base = QColor(0, 0, 0)
        base.setAlphaF(0.32)
        p.fillRect(self.rect(), base)
        p.end()

    # --------------------------------------------------------------- ack ---
    def _ack(self, action: str) -> None:
        self._esc.stop()
        self.app.audio.stop()
        self.hide()
        self.app.ack_alert(action)

    def hideEvent(self, event) -> None:  # noqa: N802
        self._esc.stop()
        super().hideEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._ack("next")
        else:
            super().keyPressEvent(event)
