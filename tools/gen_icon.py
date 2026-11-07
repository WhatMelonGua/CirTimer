"""Design + render the 超能苹果钟 icon (line-art apple + clock + free loop).

Two treatments are produced:
  * ``appleclock.svg``       line art on transparent (in-app branding, light bg)
  * ``appleclock-badge.svg`` white line art on a rounded accent square
                             (tray / taskbar / .ico — stays visible on a dark
                             taskbar where dark strokes would disappear)

Run:  envs\\.venv\\Scripts\\python.exe tools\\gen_icon.py
"""
from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "icon"

ACCENT = "#2B6CF6"
INK = "#1B1B1B"


def shapes(stroke: float, color: str) -> str:
    """Apple + leaf + clock, in a 100x100 box."""
    return f"""
    <g fill="none" stroke="{color}" stroke-width="{stroke}"
       stroke-linecap="round" stroke-linejoin="round">
      <path d="M50 41
               C46 33 34 32 28 41
               C22 51 24 69 36 76
               C44 80.5 56 80.5 64 76
               C76 69 78 51 72 41
               C66 32 54 33 50 41 Z"/>
      <path d="M50 41 C50 35 51 30 53 25.5"/>
      <path d="M53.5 30 C58 21.5 67.5 20.5 70.5 25 C68 32.5 58.5 33.5 53.5 30 Z"/>
      <circle cx="50" cy="59" r="12.6"/>
      <path d="M50 59 L50 50.6"/>
      <path d="M50 59 L56.4 59"/>
    </g>
    <circle cx="50" cy="59" r="1.8" fill="{color}"/>
    """


def loop_arc(stroke: float, color: str) -> str:
    """A cradle-like arc under the fruit with an arrow head: 'keep cycling'."""
    return f"""
    <g fill="none" stroke="{color}" stroke-width="{stroke}"
       stroke-linecap="round" stroke-linejoin="round">
      <path d="M76 73 C70 84 30 84 21 69"/>
      <path d="M21 69 L19.2 61.4 M21 69 L28.6 67.4"/>
    </g>
    """


def plain_svg(color: str = INK, stroke: float = 4.0) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     width="100" height="100">
{shapes(stroke, color)}
{loop_arc(stroke * 0.9, color)}
</svg>
"""


def badge_svg(color: str = ACCENT, stroke: float = 6.4) -> str:
    """White line art on a rounded square — legible on any taskbar."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"
     width="100" height="100">
  <rect x="0" y="0" width="100" height="100" rx="23" fill="{color}"/>
  <g transform="translate(16 16) scale(0.68)">
{shapes(stroke, "#FFFFFF")}
{loop_arc(stroke * 0.9, "#FFFFFF")}
  </g>
</svg>
"""


def render(svg: str, size: int) -> QImage:
    renderer = QSvgRenderer(svg.encode("utf-8"))
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def contact_sheet() -> QImage:
    sizes = [256, 96, 48, 32, 16]
    pad = 18
    tiles = [
        ("plain / white bg", plain_svg(), "#FFFFFF", "#FFFFFF"),
        ("plain / dark bg", plain_svg("#FFFFFF"), "#1E1E1E", "#1E1E1E"),
        ("badge / dark bg", badge_svg(), "#1E1E1E", "#1E1E1E"),
        ("badge / light bg", badge_svg(), "#F3F3F3", "#F3F3F3"),
    ]
    width = pad + sum(s + pad for s in sizes)
    height = pad + len(tiles) * (256 + pad)
    sheet = QImage(width, height, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("#FFFFFF"))
    p = QPainter(sheet)
    for row, (_name, svg, bg, _fill) in enumerate(tiles):
        y = pad + row * (256 + pad)
        p.fillRect(pad, y, width - 2 * pad, 256, QColor(bg))
        x = pad
        for size in sizes:
            p.drawImage(x, y + (256 - size) // 2, render(svg, size))
            x += size + pad
    p.end()
    return sheet


def write_ico(images: list[QImage], path: Path) -> None:
    payloads = []
    for img in images:
        tmp = path.with_suffix(f".{img.width()}.png")
        img.save(str(tmp), "PNG")
        payloads.append((img.width(), tmp.read_bytes()))
        tmp.unlink()

    header = struct.pack("<HHH", 0, 1, len(payloads))
    offset = 6 + 16 * len(payloads)
    entries = b""
    data = b""
    for size, blob in payloads:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        data += blob
    path.write_bytes(header + entries + data)


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    ASSETS.mkdir(parents=True, exist_ok=True)

    plain = plain_svg()
    badge = badge_svg()
    (ASSETS / "appleclock.svg").write_text(plain, encoding="utf-8")
    (ASSETS / "appleclock-badge.svg").write_text(badge, encoding="utf-8")
    for size in (16, 24, 32, 48, 64, 128, 256):
        render(plain, size).save(str(ASSETS / f"appleclock-{size}.png"), "PNG")
        render(badge, size).save(str(ASSETS / f"appleclock-badge-{size}.png"), "PNG")
    write_ico([render(badge, s) for s in (16, 24, 32, 48, 64, 128, 256)],
              ASSETS / "appleclock.ico")

    shots = ROOT / "docs" / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    contact_sheet().save(str(shots / "icon-candidates.png"), "PNG")
    print("wrote", ASSETS / "appleclock.svg", "and", ASSETS / "appleclock.ico")


if __name__ == "__main__":
    main()
