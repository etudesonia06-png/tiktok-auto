"""Musique de fond originale, générée à chaque vidéo (aucun droit d'auteur) :
boucle rythmée façon « sketch foot » ou plus douce pour la série."""
import wave
from pathlib import Path

import numpy as np

SR = 32000
# progressions (demi-tons par rapport à la tonique) et tempo selon le mode
STYLES = {
    "football": dict(bpm=104, root=45, prog=[0, 5, 3, 7], minor=True, drums=True),
    "trend": dict(bpm=110, root=48, prog=[0, 7, 9, 5], minor=False, drums=True),
    "series": dict(bpm=78, root=50, prog=[0, 8, 3, 10], minor=True, drums=False),
}


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _note(f, dur, kind="pluck"):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "bass":
        x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(4 * np.pi * f * t)
        e = np.exp(-t * 3.5)
    elif kind == "pad":
        x = sum(np.sin(2 * np.pi * f * d * t) for d in (0.997, 1.0, 1.003)) / 3
        e = np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.3)
    else:
        x = np.sign(np.sin(2 * np.pi * f * t)) * 0.4 + np.sin(2 * np.pi * f * t) * 0.6
        e = np.exp(-t * 9)
    return (x * e).astype(np.float32)


def make(seconds: float, mode: str, dest: Path, seed: int = 0) -> Path:
    st = STYLES.get(mode, STYLES["football"])
    rng = np.random.default_rng(seed)
    beat = 60 / st["bpm"]
    n = int((seconds + 1) * SR)
    out = np.zeros(n, np.float32)

    def add(sig, t, g):
        i = int(t * SR)
        if i < n:
            out[i:i + len(sig)] += g * sig[: n - i]

    third = 3 if st["minor"] else 4
    bar = 4 * beat
    t = 0.0
    k = 0
    while t < seconds:
        r = st["root"] + st["prog"][k % len(st["prog"])]
        chord = [r + 12, r + 12 + third, r + 19]
        for m in chord:
            add(_note(_hz(m), bar, "pad"), t, 0.10)
        for b in range(8):  # basse en croches
            if b in (0, 3, 4, 6):
                add(_note(_hz(r - 12 + (12 if b == 6 else 0)), beat * 0.45, "bass"), t + b * beat / 2, 0.32)
        for b in range(8):  # petite mélodie arpégée
            if rng.random() < 0.55:
                add(_note(_hz(chord[rng.integers(0, 3)] + 12), beat * 0.4), t + b * beat / 2, 0.06)
        if st["drums"]:
            for b in range(4):
                tt = np.arange(int(0.25 * SR)) / SR
                kick = np.sin(2 * np.pi * (50 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 9)
                add(kick.astype(np.float32), t + b * beat, 0.55)
                if b % 2 == 1:
                    sn = rng.standard_normal(int(0.18 * SR)).astype(np.float32) * np.exp(-tt[: int(0.18 * SR)] * 18)
                    add(sn, t + b * beat, 0.16)
            for h in range(8):
                hh = rng.standard_normal(int(0.04 * SR)).astype(np.float32)
                hh = np.diff(hh, prepend=0) * np.exp(-np.arange(len(hh)) / SR * 90)
                add(hh.astype(np.float32), t + h * beat / 2, 0.07)
        t += bar
        k += 1
    out = out[: int(seconds * SR)]
    fade = int(1.5 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)
    out /= np.abs(out).max() + 1e-6
    pcm = (np.tanh(out * 1.2) * 0.8 * 32767).astype(np.int16)
    with wave.open(str(dest), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    return dest
