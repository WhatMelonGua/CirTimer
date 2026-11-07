"""Synthesise the built-in chimes (no third-party audio, no licence issues).

Run:  envs\\.venv\\Scripts\\python.exe tools\\gen_sounds.py
Writes 16-bit mono WAV files into assets/sounds/.
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SR = 44100
OUT = Path(__file__).resolve().parent.parent / "assets" / "sounds"


def env(i: int, n: int, attack: float = 0.01, decay: float = 3.5) -> float:
    t = i / n
    a = min(1.0, t / attack) if attack > 0 else 1.0
    return a * math.exp(-decay * t)


def tone(freq: float, dur: float, amp: float = 0.5, decay: float = 3.5,
         harmonics: tuple[tuple[float, float], ...] = ((1.0, 1.0),)) -> list[float]:
    n = int(SR * dur)
    out = []
    for i in range(n):
        e = env(i, n, 0.008, decay)
        s = 0.0
        for mult, weight in harmonics:
            s += weight * math.sin(2 * math.pi * freq * mult * i / SR)
        out.append(amp * e * s)
    return out


def mix(*tracks: list[float]) -> list[float]:
    n = max(len(t) for t in tracks)
    out = [0.0] * n
    for t in tracks:
        for i, v in enumerate(t):
            out[i] += v
    return out


def concat(*tracks: list[float], gap: float = 0.0) -> list[float]:
    out: list[float] = []
    pad = int(SR * gap)
    for t in tracks:
        out.extend(t)
        out.extend([0.0] * pad)
    return out


def write(name: str, samples: list[float], peak: float = 0.85) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    mx = max(1e-9, max(abs(s) for s in samples))
    gain = peak / mx
    frames = bytearray()
    for s in samples:
        v = int(max(-1.0, min(1.0, s * gain)) * 32767)
        frames.extend(struct.pack("<h", v))
    path = OUT / name
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(frames))
    print(f"{path.name:18s} {len(samples) / SR:5.2f}s  {len(frames) / 1024:7.1f} KB")


def main() -> None:
    # soft bell: two strikes, warm partials
    bell = lambda f=880: tone(f, 1.15, 0.6, 3.2,
                              ((1.0, 1.0), (2.0, 0.42), (2.76, 0.22), (5.4, 0.08)))
    write("bell_soft.wav", concat(bell(784), bell(784), gap=0.06))

    # rising two-note chime for breaks
    up = concat(tone(659.25, 0.55, 0.55, 3.0, ((1.0, 1.0), (2.0, 0.3))),
                tone(987.77, 0.85, 0.5, 2.6, ((1.0, 1.0), (2.0, 0.28), (3.0, 0.12))),
                gap=0.03)
    write("chime_up.wav", up)

    # water drop: quick downward pitch bend
    drop_n = int(SR * 0.5)
    drop = []
    phase = 0.0
    for i in range(drop_n):
        t = i / drop_n
        f = 1400 * math.exp(-3.2 * t) + 380
        phase += 2 * math.pi * f / SR
        drop.append(0.6 * math.exp(-6.5 * t) * math.sin(phase))
    write("water_drop.wav", drop)

    # tiny tick for 20-20-20 style reminders
    tick = concat(tone(1760, 0.09, 0.5, 14.0), tone(1320, 0.09, 0.35, 14.0), gap=0.05)
    write("tick_soft.wav", tick)

    # firmer alarm used when the user ignored the first chime
    strong = concat(tone(880, 0.22, 0.7, 6.0, ((1.0, 1.0), (1.5, 0.25))),
                    tone(660, 0.22, 0.7, 6.0, ((1.0, 1.0), (1.5, 0.25))),
                    tone(880, 0.35, 0.7, 4.0, ((1.0, 1.0), (1.5, 0.25))),
                    gap=0.08)
    write("alert_strong.wav", strong)


if __name__ == "__main__":
    main()
