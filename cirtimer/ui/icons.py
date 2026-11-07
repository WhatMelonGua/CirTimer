"""Draw the app / tray icon with QPainter (no image assets needed)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

def _pixmap(color: str, progress: float = 0.72, size: int = 64) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pad = size * 0.12
    rect = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
    thick = max(2.0, size * 0.12)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(color).lighter(150), thick, Qt.PenStyle.SolidLine,
                  Qt.PenCapStyle.RoundCap))
    p.drawArc(rect, 0, 360 * 16)
    p.setPen(QPen(QColor(color), thick, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.drawArc(rect, 90 * 16, int(-360 * 16 * progress))
    p.end()
    return pm


def make_icon(color: str, progress: float = 0.72) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_pixmap(color, progress, size))
    return icon


ICON_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icon"


def app_icon() -> QIcon:
    """The 超能苹果钟 badge icon; falls back to a drawn ring when missing."""
    ico = ICON_DIR / "appleclock.ico"
    if ico.is_file():
        icon = QIcon(str(ico))
        if not icon.isNull():
            return icon
    return make_icon("#2B6CF6")


def brand_pixmap(size: int = 26) -> QPixmap:
    for name in (f"appleclock-badge-{64}.png", "appleclock-badge-128.png"):
        path = ICON_DIR / name
        if path.is_file():
            pm = QPixmap(str(path))
            if not pm.isNull():
                return pm.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    return _pixmap("#2B6CF6", 0.72, size)


def svg_pixmap(path, size: int, color: str | None = None, device_ratio: float = 2.0) -> QPixmap:
    """Render an SVG file to a pixmap, optionally recoloured to *color*."""
    from PySide6.QtSvg import QSvgRenderer

    px = max(8, int(size * device_ratio))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    if path is None:
        return pm
    renderer = QSvgRenderer(str(path))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p, QRectF(0, 0, px, px))
    p.end()
    if color:
        tint = QPixmap(px, px)
        tint.fill(QColor(color))
        p = QPainter(pm)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        p.drawPixmap(0, 0, tint)
        p.end()
    pm.setDevicePixelRatio(device_ratio)
    return pm
