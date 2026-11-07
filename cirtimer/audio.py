"""Chime playback (wav / mp3 / ogg) via QtMultimedia, looping until acknowledged."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from .config import project_root

SOUND_DIR = project_root() / "assets" / "sounds"

# phase kind -> default chime file
DEFAULT_BY_KIND = {
    "focus": "bell_soft.wav",
    "break": "chime_up.wav",
    "move": "chime_up.wav",
    "stretch": "bell_soft.wav",
    "eye": "tick_soft.wav",
    "water": "water_drop.wav",
    "custom": "bell_soft.wav",
}


def resolve_sound(phase, settings) -> Path | None:
    """Return the sound file for a phase, or None when muted/missing."""
    if not getattr(settings, "sound_enabled", True):
        return None
    explicit = (getattr(phase, "sound", "") or "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
    name = DEFAULT_BY_KIND.get(getattr(phase, "kind", "custom"), "bell_soft.wav")
    p = SOUND_DIR / name
    return p if p.is_file() else None


class Audio:
    def __init__(self) -> None:
        self._player = QMediaPlayer()
        self._out = QAudioOutput()
        self._player.setAudioOutput(self._out)
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._player.errorOccurred.connect(self._on_error)
        self._playing = False
        self.last_error = ""

    def _on_error(self, _error, message: str) -> None:
        self.last_error = message or "无法播放该音频"
        self._playing = False

    def play(self, path: Path | str | None, volume: int = 60) -> None:
        if not path:
            return
        p = Path(path)
        if not p.is_file():
            self.last_error = f"文件不存在：{p}"
            return
        self.last_error = ""
        self._out.setVolume(max(0.0, min(1.0, volume / 100.0)))
        if self._playing:
            # switching source while the decoder is still spinning up can block
            self._player.stop()
        self._player.setLoops(QMediaPlayer.Loops.Infinite)
        self._player.setSource(QUrl.fromLocalFile(str(p)))
        self._player.play()
        self._playing = True

    def stop(self) -> None:
        if self._playing:
            self._player.stop()
            self._playing = False

    def preview(self, path: Path | str | None, volume: int = 60) -> None:
        self.stop()
        if not path:
            self.last_error = "没有选择铃声"
            return
        p = Path(path)
        if not p.is_file():
            self.last_error = f"文件不存在：{p}"
            return
        self.last_error = ""
        self._out.setVolume(max(0.0, min(1.0, volume / 100.0)))
        self._player.setLoops(QMediaPlayer.Loops.Once)
        self._player.setSource(QUrl.fromLocalFile(str(p)))
        self._player.play()
        self._playing = True

    @property
    def is_playing(self) -> bool:
        return self._playing
