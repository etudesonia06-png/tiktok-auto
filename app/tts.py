"""Voix off française naturelle avec Microsoft Edge TTS (gratuit, sans clé),
avec horodatage mot par mot pour des sous-titres synchronisés."""
import asyncio
import re
import subprocess
from pathlib import Path

from . import config


def _probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


async def _edge(text: str, mp3: Path, voice: str) -> list[tuple[float, float, str]]:
    import edge_tts
    try:
        com = edge_tts.Communicate(text, voice, rate=config.VOICE_RATE, boundary="WordBoundary")
    except TypeError:  # anciennes versions
        com = edge_tts.Communicate(text, voice, rate=config.VOICE_RATE)
    words = []
    with open(mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append((s, s + chunk["duration"] / 1e7, chunk["text"]))
    return words


def _estimate_words(text: str, total: float) -> list[tuple[float, float, str]]:
    toks = text.split()
    weights = [max(len(re.sub(r"\W", "", t)), 2) for t in toks]
    scale = (total - 0.2) / sum(weights)
    t, out = 0.1, []
    for tok, w in zip(toks, weights):
        out.append((t, t + w * scale, tok))
        t += w * scale
    return out


def _silent(seconds: float, path: Path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "4", str(path)],
                   check=True)


def _align_punctuation(text: str, words: list[tuple[float, float, str]]):
    """Edge renvoie les mots sans ponctuation : on réutilise les jetons du texte original
    (avec virgules, ?, €…) pour un affichage propre."""
    toks = text.split()
    if len(toks) == len(words):
        return [(s, e, tok) for (s, e, _), tok in zip(words, toks)]
    return words


def synthesize(scenes: list[dict], workdir: Path) -> list[dict]:
    """Ajoute à chaque scène : audio, duration, words (relatifs à la scène)."""
    workdir.mkdir(parents=True, exist_ok=True)
    for i, sc in enumerate(scenes):
        text = sc["narration"].strip()
        mp3 = workdir / f"voice_{i:02d}.mp3"
        words = None
        if not config.OFFLINE:
            try:
                words = asyncio.run(asyncio.wait_for(_edge(text, mp3, sc.get("voice") or config.VOICE), timeout=60))
            except Exception as e:
                print(f"[voix] Edge TTS indisponible ({e}), voix muette de secours")
        if words is None:
            est = max(1.5, len(text.split()) / 2.7)
            _silent(est, mp3)
            words = []
        dur = _probe_duration(mp3)
        if not words:
            words = _estimate_words(text, dur)
        sc.update(audio=str(mp3), duration=dur + 0.15, words=_align_punctuation(text, words))
    return scenes
