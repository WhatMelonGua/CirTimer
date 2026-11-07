"""Theme packs (themes/*.json) -> palette dict + Qt stylesheet."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import project_root

DEFAULT_THEME = "fluent-light"

_FALLBACK: dict[str, Any] = {
    "id": DEFAULT_THEME,
    "name": "Fluent 浅色",
    "base": "light",
    "palette": {
        "bg": "#F3F3F3",
        "surface": "#FFFFFF",
        "surface_alt": "#FAFAFA",
        "sidebar": "#FFFFFF",
        "border": "#E3E3E3",
        "border_strong": "#D0D0D0",
        "text": "#1B1B1B",
        "text_sub": "#5F5F5F",
        "text_faint": "#8C8C8C",
        "accent": "#0F6CBD",
        "accent_text": "#FFFFFF",
        "success": "#0F7B0F",
        "warning": "#B8720A",
        "danger": "#C42B1C",
        "ring_track": "#E8E8E8",
    },
    "radius": {"card": 8, "pill": 18, "small": 6},
    "font": {"ui": "Microsoft YaHei UI", "num": "Segoe UI Variable Display",
             "num_size": 54, "ui_size": 12},
    "effects": {"ring_glow": False},
}


def theme_dir() -> Path:
    return project_root() / "themes"


def list_themes() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    d = theme_dir()
    if d.exists():
        for f in sorted(d.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if "id" not in data:
                data["id"] = f.stem
            data.setdefault("name", f.stem)
            out.append(data)
    if not out:
        out.append(dict(_FALLBACK))
    return out


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_theme(theme_id: str | None, accent_override: str = "") -> dict[str, Any]:
    chosen = None
    for t in list_themes():
        if t.get("id") == theme_id:
            chosen = t
            break
    theme = _merge(_FALLBACK, chosen or {})
    if accent_override:
        theme["palette"]["accent"] = accent_override
    return theme


# ------------------------------------------------------------------ utils ---
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgba(value: str, pct: float) -> str:
    r, g, b = hex_to_rgb(value)
    return f"rgba({r}, {g}, {b}, {max(0.0, min(1.0, pct)) * 100:.0f}%)"


def pal(theme: dict[str, Any], key: str, default: str = "#000000") -> str:
    return str(theme.get("palette", {}).get(key, default))


def build_qss(theme: dict[str, Any]) -> str:
    p = theme["palette"]
    r = theme["radius"]
    f = theme["font"]
    bg, surface, alt = p["bg"], p["surface"], p["surface_alt"]
    border, strong = p["border"], p["border_strong"]
    text, sub, faint = p["text"], p["text_sub"], p["text_faint"]
    accent, accent_text = p["accent"], p["accent_text"]
    ui, ui_size = f["ui"], f["ui_size"]
    check = (theme_dir().parent / "assets" / "icons" / "check.svg").as_posix()

    return f"""
* {{ outline: none; }}
QWidget {{
    font-family: "{ui}";
    font-size: {ui_size}px;
    color: {text};
}}
QWidget#Root, QMainWindow {{ background: {bg}; }}
QDialog {{ background: {bg}; }}

/* ---------------- generic button (dialogs, fallbacks) ---------------- */
QPushButton {{
    background: {surface};
    color: {text};
    border: 1px solid {strong};
    border-radius: {r['small']}px;
    padding: 6px 14px;
}}
QPushButton:hover {{ background: {alt}; }}
QPushButton:pressed {{ background: {border}; }}
QPushButton:disabled {{ color: {faint}; }}
QPushButton#Swatch {{
    background: transparent;
    border: none;
    padding: 0;
}}
QPushButton#Emoji {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {r['small']}px;
    padding: 0;
    font-family: "Segoe UI Emoji";
    font-size: 15px;
}}
QPushButton#Emoji:hover {{ background: {alt}; border-color: {accent}; }}

/* ---------------- item views ---------------- */
QListWidget, QListView, QTreeView {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {r['small']}px;
    padding: 4px;
}}
QListWidget::item, QListView::item {{
    padding: 5px 6px;
    border-radius: 4px;
    color: {text};
}}
QListWidget::item:hover, QListView::item:hover {{ background: {rgba(text, 0.04)}; }}
QListWidget::item:selected, QListView::item:selected {{
    background: {rgba(accent, 0.14)};
    color: {text};
}}

/* ---------------- sidebar ---------------- */
QWidget#Sidebar {{
    background: {p['sidebar']};
    border-right: 1px solid {border};
}}
QLabel#Brand {{ font-size: 15px; font-weight: 600; color: {text}; }}
QLabel#BrandSub {{ font-size: 11px; color: {faint}; }}

QPushButton#Nav {{
    text-align: left;
    padding: 8px 12px;
    border: 1px solid transparent;
    border-radius: {r['small']}px;
    background: transparent;
    color: {sub};
    font-size: {ui_size}px;
}}
QPushButton#Nav:hover {{ background: {rgba(text, 0.05)}; color: {text}; }}
QPushButton#Nav:checked {{
    background: {rgba(accent, 0.10)};
    color: {accent};
    font-weight: 600;
}}

/* ---------------- cards ---------------- */
QFrame#Card {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {r['card']}px;
}}
QFrame#CardFlat {{
    background: {alt};
    border: 1px solid {border};
    border-radius: {r['card']}px;
}}
QLabel#H1 {{ font-size: 20px; font-weight: 600; }}
QLabel#H2 {{ font-size: 14px; font-weight: 600; }}
QLabel#Muted {{ color: {sub}; }}
QLabel#Faint {{ color: {faint}; font-size: 11px; }}
QLabel#BigNum {{
    font-family: "{f['num']}";
    font-size: {f['num_size']}px;
    font-weight: 600;
}}

/* ---------------- buttons ---------------- */
QPushButton#Primary {{
    background: {accent};
    color: {accent_text};
    /* a real (same-colour) border is required for Qt to honour border-radius */
    border: 1px solid {accent};
    border-radius: {r['pill']}px;
    padding: 9px 26px;
    font-size: {ui_size}px;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: {rgba(accent, 0.86)}; border-color: {rgba(accent, 0.86)}; }}
QPushButton#Primary:pressed {{ background: {rgba(accent, 0.74)}; border-color: {rgba(accent, 0.74)}; }}
QPushButton#Primary:disabled {{ background: {border}; border-color: {border}; color: {faint}; }}

QPushButton#Ghost {{
    background: transparent;
    color: {text};
    border: 1px solid {strong};
    border-radius: {r['pill']}px;
    padding: 9px 20px;
    font-size: {ui_size}px;
}}
QPushButton#Ghost:hover {{ background: {rgba(text, 0.05)}; }}
QPushButton#Ghost:disabled {{ color: {faint}; border-color: {border}; }}

QPushButton#Link {{
    background: transparent;
    border: none;
    color: {accent};
    padding: 4px 6px;
}}
QPushButton#Link:hover {{ text-decoration: underline; }}

QPushButton#Danger {{
    background: transparent;
    border: 1px solid {strong};
    border-radius: {r['pill']}px;
    color: {text};
    padding: 9px 22px;
}}
QPushButton#Danger:hover {{
    background: {p['danger']};
    border-color: {p['danger']};
    color: #FFFFFF;
}}
QPushButton#Danger:pressed {{ background: {rgba(p['danger'], 0.8)}; border-color: {rgba(p['danger'], 0.8)}; }}

QPushButton#QuitLink {{
    background: transparent;
    border: none;
    color: {faint};
    padding: 5px 6px;
    text-align: left;
}}
QPushButton#QuitLink:hover {{
    color: {p['danger']};
    text-decoration: underline;
}}

QStatusBar {{
    background: {surface};
    color: {sub};
    border-top: 1px solid {border};
}}

/* ---------------- inputs ---------------- */
QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit, QDateTimeEdit,
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: {surface};
    border: 1px solid {strong};
    border-radius: {r['small']}px;
    padding: 6px 10px;
    min-height: 18px;
    selection-background-color: {rgba(accent, 0.25)};
}}
QPlainTextEdit, QTextEdit {{ padding: 6px 8px; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {surface};
    border: 1px solid {border};
    selection-background-color: {rgba(accent, 0.12)};
    selection-color: {text};
    padding: 4px;
}}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid {strong};
    background: {surface};
}}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: url("{check}");
}}
QSpinBox#Spin, QDoubleSpinBox#Spin {{ padding-right: 26px; }}
/* native steppers are replaced by NumberBox/DecimalBox's own +/- buttons */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
    background: transparent;
}}
QToolButton#SpinStep {{
    border: none;
    background: transparent;
    color: {sub};
    font-size: 12px;
    font-weight: 600;
    padding: 0;
}}
QToolButton#SpinStep:hover {{
    background: {rgba(accent, 0.16)};
    color: {accent};
    border-radius: 4px;
}}
QToolButton#SpinStep:pressed {{ background: {rgba(accent, 0.28)}; }}
QSlider::groove:horizontal {{
    height: 4px; background: {border}; border-radius: 2px;
}}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0;
    border-radius: 7px; background: {accent}; border: 2px solid {surface};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {rgba(text, 0.18)}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {rgba(text, 0.3)}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{
    background: {surface}; color: {text};
    border: 1px solid {border}; padding: 4px 8px;
}}
QMenu {{
    background: {surface};
    border: 1px solid {border};
    border-radius: {r['small']}px;
    padding: 4px;
}}
QMenu::item {{ padding: 6px 20px 6px 14px; border-radius: 4px; }}
QMenu::item:selected {{ background: {rgba(accent, 0.12)}; color: {text}; }}
QMenu::separator {{ height: 1px; background: {border}; margin: 4px 8px; }}
"""
