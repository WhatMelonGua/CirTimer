"""Always-on-top mini HUD: a small ring + countdown you can park in a corner."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget


class HudWindow(QWidget):
    def __init__(self, app) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.app = app
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(224, 60)
        self.setToolTip("拖动移动位置 · 双击打开 CirClock")
        self._time = "00:00"
        self._name = "未开始"
        self._progress = 0.0
        self._color = QColor(self.app.theme["palette"]["accent"])
        self._drag: QPoint | None = None
        self.restore_position()

    # ------------------------------------------------------------- layout ---
    def restore_position(self) -> None:
        pos = self.app.cfg.settings.hud_pos
        screen = QGuiApplication.primaryScreen().availableGeometry()
        if pos and pos[0] >= 0 and pos[1] >= 0:
            self.move(pos[0], pos[1])
        else:
            self.move(screen.right() - self.width() - 32, screen.bottom() - self.height() - 96)

    def _save_position(self) -> None:
        self.app.cfg.settings.hud_pos = [self.x(), self.y()]
        self.app.save()

    # -------------------------------------------------------------- state ---
    def update_state(self, time_text: str, name: str, progress: float, color: str) -> None:
        self._time = time_text
        self._name = name
        self._progress = max(0.0, min(1.0, progress))
        if color:
            self._color = QColor(color)
        self.update()

    def restyle(self) -> None:
        self._color = QColor(self.app.theme["palette"]["accent"])
        self.update()

    # -------------------------------------------------------------- paint ---
    def paintEvent(self, event) -> None:  # noqa: N802
        pal = self.app.theme["palette"]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        bg = QColor(pal["surface"])
        bg.setAlphaF(0.94)
        p.setBrush(bg)
        p.setPen(QPen(QColor(pal["border"]), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12)

        cx, cy, r = 30.0, self.height() / 2, 15.0
        rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(pal["ring_track"]), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)
        if self._progress > 0.001:
            p.setPen(QPen(self._color, 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 90 * 16, int(-360 * 16 * self._progress))

        ui = str(self.app.theme.get("font", {}).get("ui", "Microsoft YaHei UI"))
        num = str(self.app.theme.get("font", {}).get("num", "Segoe UI Variable Display"))

        f = QFont(num)
        f.setPixelSize(19)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(QColor(pal["text"]))
        p.drawText(QRectF(56, 8, 160, 24), int(Qt.AlignmentFlag.AlignLeft
                                               | Qt.AlignmentFlag.AlignVCenter), self._time)

        f = QFont(ui)
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(pal["text_sub"]))
        p.drawText(QRectF(56, 31, 160, 20), int(Qt.AlignmentFlag.AlignLeft
                                                | Qt.AlignmentFlag.AlignVCenter), self._name)
        p.end()

    # --------------------------------------------------------------- drag ---
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self._save_position()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.app.show_window()
