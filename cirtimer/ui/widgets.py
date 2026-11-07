"""Reusable widgets: progress ring, stat chips, cards, weekly bar chart."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


def qcolor(value: str, alpha: float = 1.0) -> QColor:
    c = QColor(value)
    if alpha < 1.0:
        c.setAlphaF(alpha)
    return c


def format_seconds(seconds: float) -> str:
    s = int(round(max(0.0, seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, flat: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat" if flat else "Card")


class StatChip(QFrame):
    """Small value + caption block used in the today-summary row."""

    def __init__(self, caption: str, value: str = "—", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CardFlat")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        self.value = QLabel(value)
        self.value.setObjectName("H2")
        self.caption = QLabel(caption)
        self.caption.setObjectName("Faint")
        lay.addWidget(self.value)
        lay.addWidget(self.caption)

    def set_value(self, text: str) -> None:
        self.value.setText(text)


class RingWidget(QWidget):
    """Big circular progress with the phase icon, remaining time and labels."""

    def __init__(self, theme: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._color = QColor(theme["palette"]["accent"])
        self._track = QColor(theme["palette"]["ring_track"])
        self._text = QColor(theme["palette"]["text"])
        self._muted = QColor(theme["palette"]["text_sub"])
        self._progress = 0.0
        self._time_text = "00:00"
        self._name = "未开始"
        self._sub = ""
        self._icon = ""
        self._paused = False
        self._glow = bool(theme.get("effects", {}).get("ring_glow", False))
        self.setMinimumSize(300, 300)

    # -- api
    def set_theme(self, theme: dict) -> None:
        self._theme = theme
        self._color = QColor(theme["palette"]["accent"])
        self._track = QColor(theme["palette"]["ring_track"])
        self._text = QColor(theme["palette"]["text"])
        self._muted = QColor(theme["palette"]["text_sub"])
        self._glow = bool(theme.get("effects", {}).get("ring_glow", False))
        self.update()

    def set_phase_color(self, color: str) -> None:
        if color:
            self._color = QColor(color)
            self.update()

    def set_content(self, *, time_text: str | None = None, name: str | None = None,
                    sub: str | None = None, icon: str | None = None,
                    progress: float | None = None, paused: bool | None = None) -> None:
        if time_text is not None:
            self._time_text = time_text
        if name is not None:
            self._name = name
        if sub is not None:
            self._sub = sub
        if icon is not None:
            self._icon = icon
        if progress is not None:
            self._progress = max(0.0, min(1.0, progress))
        if paused is not None:
            self._paused = paused
        self.update()

    # -- paint
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        side = min(self.width(), self.height())
        thick = max(9.0, side * 0.042)
        margin = thick / 2 + side * 0.03
        rect = QRectF((self.width() - side) / 2 + margin,
                      (self.height() - side) / 2 + margin,
                      side - 2 * margin, side - 2 * margin)
        center = rect.center()

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self._track, thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 0, 360 * 16)

        if self._progress > 0.0005:
            if self._glow:
                for i in range(4, 0, -1):
                    gcol = QColor(self._color)
                    gcol.setAlphaF(0.05 + 0.02 * (4 - i))
                    p.setPen(QPen(gcol, thick + i * 7.0, Qt.PenStyle.SolidLine,
                                  Qt.PenCapStyle.RoundCap))
                    p.drawArc(rect, 90 * 16, int(-360 * 16 * self._progress))
            pen = QPen(self._color, thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            if self._paused:
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setDashPattern([1.4, 1.4])
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, int(-360 * 16 * self._progress))

        ui_family = str(self._theme.get("font", {}).get("ui", "Microsoft YaHei UI"))
        num_family = str(self._theme.get("font", {}).get("num", "Segoe UI Variable Display"))

        if self._icon:
            f = QFont(ui_family)
            f.setPixelSize(int(side * 0.085))
            p.setFont(f)
            p.setPen(self._muted)
            p.drawText(QRectF(center.x() - 60, center.y() - side * 0.255, 120, side * 0.11),
                       int(Qt.AlignmentFlag.AlignCenter), self._icon)

        f = QFont(num_family)
        f.setPixelSize(int(side * 0.185))
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(self._text)
        p.drawText(QRectF(center.x() - side * 0.5, center.y() - side * 0.135,
                          side, side * 0.24),
                   int(Qt.AlignmentFlag.AlignCenter), self._time_text)

        f = QFont(ui_family)
        f.setPixelSize(max(11, int(side * 0.043)))
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.setPen(self._color if not self._paused else self._muted)
        p.drawText(QRectF(center.x() - side * 0.5, center.y() + side * 0.105,
                          side, side * 0.075),
                   int(Qt.AlignmentFlag.AlignCenter), self._name)

        if self._sub:
            f = QFont(ui_family)
            f.setPixelSize(max(10, int(side * 0.036)))
            p.setFont(f)
            p.setPen(self._muted)
            p.drawText(QRectF(center.x() - side * 0.5, center.y() + side * 0.175,
                              side, side * 0.07),
                       int(Qt.AlignmentFlag.AlignCenter), self._sub)
        p.end()


class WeekChart(QWidget):
    """Minimal bar chart: focus minutes per day for the last N days."""

    def __init__(self, theme: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[dict] = []
        self._theme = theme
        self.setMinimumHeight(160)

    def set_theme(self, theme: dict) -> None:
        self._theme = theme
        self.update()

    def set_data(self, data: list[dict]) -> None:
        self._data = data
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pal = self._theme["palette"]
        ui = str(self._theme.get("font", {}).get("ui", "Microsoft YaHei UI"))

        if not self._data:
            p.setPen(QColor(pal["text_faint"]))
            p.setFont(QFont(ui, 10))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "暂无数据")
            p.end()
            return

        top, bottom = 12, 26
        h = self.height() - top - bottom
        n = len(self._data)
        slot = self.width() / max(1, n)
        bar_w = min(34.0, slot * 0.45)
        peak = max([d.get("focus_minutes", 0.0) for d in self._data] + [60.0])

        p.setFont(QFont(ui, 9))
        for i, d in enumerate(self._data):
            x = slot * i + (slot - bar_w) / 2
            v = d.get("focus_minutes", 0.0)
            bh = max(2.0, h * (v / peak))
            r = QRectF(x, top + h - bh, bar_w, bh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(pal["accent"]) if v > 0 else QColor(pal["border"]))
            p.drawRoundedRect(r, 3, 3)
            p.setPen(QColor(pal["text_faint"]))
            label = d["day"][5:]
            p.drawText(QRectF(slot * i, top + h + 4, slot, 18),
                       int(Qt.AlignmentFlag.AlignCenter), label)
        p.end()
