"""Generate the built-in stick-figure action diagrams (plain SVG, no deps).

Run:  envs\\.venv\\Scripts\\python.exe tools\\gen_action_svgs.py
Writes assets/actions/<id>.svg  (viewBox 0 0 100 100, stroked line art).
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "actions"
STROKE = "#7A7A7A"
SW = 2.2


# ------------------------------------------------------------- primitives ---
def line(x1: float, y1: float, x2: float, y2: float) -> str:
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'


def poly(*pts: tuple[float, float]) -> str:
    d = " ".join(f"{x},{y}" for x, y in pts)
    return f'<polyline points="{d}"/>'


def circle(cx: float, cy: float, r: float, fill: str = "none") -> str:
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>'


def rect(x: float, y: float, w: float, h: float, r: float = 2) -> str:
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" '
            f'fill="none"/>')


def arrow(x1: float, y1: float, x2: float, y2: float, size: float = 5.0) -> str:
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    left = (x2 - size * math.cos(ang - 0.5), y2 - size * math.sin(ang - 0.5))
    right = (x2 - size * math.cos(ang + 0.5), y2 - size * math.sin(ang + 0.5))
    return (line(x1, y1, x2, y2)
            + poly((round(left[0], 2), round(left[1], 2)), (x2, y2),
                   (round(right[0], 2), round(right[1], 2))))


def dashed(x1: float, y1: float, x2: float, y2: float) -> str:
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke-dasharray="3 3" opacity="0.7"/>')


def arc(cx: float, cy: float, r: float, start: float, end: float) -> str:
    import math
    a1, a2 = math.radians(start), math.radians(end)
    x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
    x2, y2 = cx + r * math.cos(a2), cy + r * math.sin(a2)
    large = 1 if abs(end - start) > 180 else 0
    sweep = 1 if end > start else 0
    return (f'<path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} {sweep} '
            f'{x2:.1f} {y2:.1f}" fill="none"/>')


def figure(head=(50, 13), neck=(50, 21), shoulder=(50, 27), pelvis=(50, 52),
           lelbow=(43, 39), lhand=(40, 51), relbow=(57, 39), rhand=(60, 51),
           lknee=(46, 70), lfoot=(44, 89), rknee=(54, 70), rfoot=(56, 89),
           head_r: float = 6.0) -> str:
    parts = [
        circle(head[0], head[1], head_r),
        poly(neck, shoulder, pelvis),
        poly(shoulder, lelbow, lhand),
        poly(shoulder, relbow, rhand),
        poly(pelvis, lknee, lfoot),
        poly(pelvis, rknee, rfoot),
    ]
    return "".join(parts)


def chair(x: float = 24, y: float = 62) -> str:
    """Furniture hint drawn behind the figure: back post, seat, two legs."""
    return ('<g opacity="0.5">'
            + line(x, y - 26, x, y)
            + line(x, y, x + 36, y)
            + line(x + 30, y, x + 30, y + 20)
            + line(x + 3, y, x + 3, y + 20)
            + "</g>")


def floor(y: float = 90) -> str:
    return f'<line x1="8" y1="{y}" x2="92" y2="{y}" opacity="0.35"/>'


def wall(x: float = 24) -> str:
    ticks = "".join(line(x, y, x - 5, y + 4) for y in range(16, 88, 12))
    return line(x, 8, x, 92) + ticks


# ------------------------------------------------------------------ poses ---
POSES: dict[str, str] = {}

POSES["walk"] = figure(
    head=(48, 14), pelvis=(50, 52), lknee=(40, 70), lfoot=(32, 88),
    rknee=(60, 70), rfoot=(68, 86), lelbow=(44, 38), lhand=(54, 44),
    relbow=(56, 38), rhand=(44, 44)) + dashed(22, 48, 30, 48) + dashed(20, 58, 28, 58)

POSES["stand_up"] = (
    chair(30, 62)
    + figure(head=(58, 22), neck=(58, 29), shoulder=(58, 34), pelvis=(56, 56),
             lknee=(52, 72), lfoot=(50, 88), rknee=(62, 72), rfoot=(64, 88),
             lelbow=(52, 42), lhand=(48, 52), relbow=(64, 42), rhand=(68, 52))
    + arrow(76, 46, 76, 24)
)

POSES["wall_squat"] = (
    wall(26)
    + figure(head=(44, 26), neck=(43, 33), shoulder=(43, 39), pelvis=(42, 56),
             lknee=(60, 60), lfoot=(58, 82), rknee=(60, 64), rfoot=(62, 82),
             lelbow=(52, 42), lhand=(62, 44), relbow=(52, 46), rhand=(64, 50))
    + floor(84)
)

POSES["seated_ext"] = (
    chair(28, 62)
    + figure(head=(42, 28), neck=(42, 35), shoulder=(42, 40), pelvis=(44, 60),
             lknee=(62, 60), lfoot=(78, 58), rknee=(44, 76), rfoot=(44, 86),
             lelbow=(46, 46), lhand=(52, 54), relbow=(46, 50), rhand=(54, 58))
    + arrow(64, 70, 76, 70, 4.5)
)

POSES["leg_raise"] = (
    chair(28, 62)
    + figure(head=(40, 28), neck=(40, 35), shoulder=(40, 40), pelvis=(44, 60),
             lknee=(60, 52), lfoot=(74, 44), rknee=(44, 76), rfoot=(44, 86),
             lelbow=(46, 46), lhand=(52, 54), relbow=(46, 50), rhand=(54, 58))
    + arrow(52, 66, 66, 54, 4.5)
)

POSES["hamstring"] = (
    figure(head=(70, 42), neck=(64, 43), shoulder=(58, 45), pelvis=(46, 48),
           lknee=(46, 70), lfoot=(46, 89), rknee=(48, 70), rfoot=(48, 89),
           lelbow=(58, 55), lhand=(64, 66), relbow=(56, 56), rhand=(62, 68))
    + floor(90)
)

POSES["calf"] = (
    rect(30, 78, 44, 5, 1)
    + figure(head=(54, 20), neck=(54, 27), shoulder=(54, 33), pelvis=(54, 54),
             lknee=(50, 66), lfoot=(48, 78), rknee=(60, 66), rfoot=(66, 86),
             lelbow=(48, 42), lhand=(46, 52), relbow=(60, 42), rhand=(64, 52))
    + floor(92)
)

POSES["hip_flexor"] = (
    figure(head=(46, 20), neck=(46, 27), shoulder=(46, 33), pelvis=(46, 54),
           lknee=(34, 70), lfoot=(26, 88), rknee=(62, 66), rfoot=(70, 86),
           lelbow=(52, 40), lhand=(56, 26), relbow=(56, 42), rhand=(60, 28))
    + floor(90)
)

POSES["glute"] = (
    chair(28, 62)
    + figure(head=(42, 28), neck=(42, 35), shoulder=(42, 40), pelvis=(46, 60),
             lknee=(64, 58), lfoot=(54, 48), rknee=(46, 76), rfoot=(46, 86),
             lelbow=(46, 46), lhand=(52, 54), relbow=(46, 50), rhand=(54, 58))
    + arrow(58, 44, 48, 44, 4)
)

POSES["bridge"] = (
    f'<path d="M 30 74 L 38 74 L 52 54 L 70 66 L 74 80" fill="none"/>'
    + circle(26, 70, 6)
    + line(32, 72, 38, 74)
    + poly((52, 54), (70, 66), (74, 80))
    + poly((38, 74), (36, 84))
    + line(30, 86, 80, 86)
    + arrow(58, 44, 58, 34, 4)
)

POSES["kegel"] = (
    chair(26, 60)
    + figure(head=(42, 26), neck=(42, 33), shoulder=(42, 38), pelvis=(46, 58),
             lknee=(62, 58), lfoot=(62, 78), rknee=(46, 74), rfoot=(46, 86),
             lelbow=(46, 44), lhand=(52, 52), relbow=(46, 48), rhand=(54, 56))
    + dashed(50, 66, 50, 78) + arrow(50, 78, 50, 68, 4)
)

POSES["breathing"] = (
    chair(24, 60)
    + figure(head=(40, 26), neck=(40, 33), shoulder=(40, 38), pelvis=(44, 58),
             lknee=(60, 58), lfoot=(60, 78), rknee=(44, 74), rfoot=(44, 86),
             lelbow=(46, 44), lhand=(54, 52), relbow=(48, 48), rhand=(56, 56))
    + arc(58, 50, 8, -60, 60) + arc(58, 50, 13, -50, 50)
)

POSES["pelvic_tilt"] = (
    chair(26, 60)
    + figure(head=(42, 26), neck=(42, 33), shoulder=(42, 38), pelvis=(46, 58),
             lknee=(62, 58), lfoot=(62, 78), rknee=(46, 74), rfoot=(46, 86),
             lelbow=(46, 44), lhand=(52, 52), relbow=(46, 48), rhand=(54, 56))
    + arc(44, 62, 10, 120, 240) + arrow(36, 58, 34, 64, 4)
)

POSES["neck_side"] = (
    figure(head=(56, 16), neck=(50, 22), shoulder=(50, 28), pelvis=(50, 54),
           lelbow=(44, 40), lhand=(42, 52), relbow=(56, 40), rhand=(58, 52),
           lknee=(46, 72), lfoot=(44, 90), rknee=(54, 72), rfoot=(56, 90))
    + arc(50, 22, 14, -80, -20) + arrow(64, 14, 58, 11, 4)
)

POSES["shoulder_roll"] = (
    figure(head=(50, 14), neck=(50, 21), shoulder=(50, 27), pelvis=(50, 54),
           lelbow=(42, 40), lhand=(40, 52), relbow=(58, 40), rhand=(60, 52),
           lknee=(46, 72), lfoot=(44, 90), rknee=(54, 72), rfoot=(56, 90))
    + arc(38, 32, 9, -140, 60) + arc(62, 32, 9, 120, -80)
)

POSES["chest_open"] = (
    figure(head=(50, 14), neck=(50, 21), shoulder=(50, 27), pelvis=(50, 54),
           lelbow=(40, 40), lhand=(46, 48), relbow=(60, 40), rhand=(54, 48),
           lknee=(46, 72), lfoot=(44, 90), rknee=(54, 72), rfoot=(56, 90))
    + arc(50, 32, 20, 200, 340) + arrow(30, 26, 38, 26, 4) + arrow(70, 26, 62, 26, 4)
)

POSES["cat_cow"] = (
    f'<path d="M 34 52 Q 50 40 66 52" fill="none"/>'
    + f'<path d="M 34 52 Q 50 62 66 52" fill="none" opacity="0.45"/>'
    + circle(74, 46, 6)
    + poly((66, 52), (74, 46))
    + poly((66, 52), (66, 74)) + poly((66, 74), (62, 84))
    + poly((34, 52), (34, 74)) + poly((34, 74), (30, 84))
    + line(22, 86, 82, 86)
    + arrow(50, 30, 50, 40, 4)
)

POSES["eye_2020"] = (
    f'<path d="M 18 50 Q 42 28 66 50 Q 42 72 18 50 Z" fill="none"/>'
    + circle(42, 50, 7)
    + circle(42, 50, 2.5, "#7A7A7A")
    + dashed(70, 50, 84, 50)
    + circle(88, 50, 6)
    + line(88, 44, 88, 50)
    + line(88, 50, 91, 50)
    + dashed(18, 24, 34, 24) + dashed(66, 76, 82, 76)
)

POSES["eye_palm"] = (
    '<path d="M 30 46 Q 50 30 70 46 Q 50 62 30 46 Z" fill="none" opacity="0.5"/>'
    + '<path d="M 34 44 Q 50 36 66 44" fill="none"/>'
    + '<path d="M 36 52 Q 50 60 64 52" fill="none"/>'
    + '<path d="M 30 44 Q 24 34 32 28 Q 40 24 45 32" fill="none"/>'
    + '<path d="M 70 44 Q 76 34 68 28 Q 60 24 55 32" fill="none"/>'
)


def build(action_id: str, body: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
        'width="100" height="100">\n'
        f'<g stroke="{STROKE}" stroke-width="{SW}" stroke-linecap="round" '
        'stroke-linejoin="round" fill="none">\n'
        f"{body}\n</g>\n</svg>\n"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for action_id, body in POSES.items():
        path = OUT / f"{action_id}.svg"
        path.write_text(build(action_id, body), encoding="utf-8")
        print(f"wrote {path.name}")


if __name__ == "__main__":
    main()
