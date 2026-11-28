"""Voix off française naturelle avec Microsoft Edge TTS (gratuit, sans clé),
avec horodatage mot par mot pour des sous-titres synchronisés."""
import asyncio
import os
import re
import subprocess
from pathlib import Path

from . import config


def _probe_duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


async def _edge(text: str, mp3: Path, voice: str, rate: str = "", pitch: str = "") -> list[tuple[float, float, str]]:
    import edge_tts
    kw = {"rate": rate or config.VOICE_RATE, "pitch": pitch or "+0Hz"}
    try:
        com = edge_tts.Communicate(text, voice, boundary="WordBoundary", **kw)
    except TypeError:  # anciennes versions
        com = edge_tts.Communicate(text, voice, **kw)
    words = []
    with open(mp3, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append((s, s + chunk["duration"] / 1e7, chunk["text"]))
    return words


PIPER_VOICES = {  # voix françaises Piper (gratuites, hors ligne) — secours si Edge est indisponible
    "male": "fr/fr_FR/tom/medium/fr_FR-tom-medium",
    "female": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
}
FEMALE = ("Denise", "Eloise", "Vivienne")


def _piper(text: str, out: Path, voice: str, pitch: str = ""):
    """Synthèse Piper puis léger changement de hauteur pour distinguer les personnages."""
    import urllib.request
    import wave as _w
    from piper import PiperVoice
    base = Path(os.getenv("PIPER_DIR", Path.home() / ".piper"))
    base.mkdir(parents=True, exist_ok=True)
    rel = PIPER_VOICES["female" if any(f in voice for f in FEMALE) else "male"]
    model = base / (rel.split("/")[-1] + ".onnx")
    for ext in (".onnx", ".onnx.json"):
        f = base / (rel.split("/")[-1] + ext)
        if not f.exists():
            urllib.request.urlretrieve(f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{rel}{ext}", f)
    wav = out.with_suffix(".piper.wav")
    v = PiperVoice.load(str(model))
    with _w.open(str(wav), "wb") as wf:
        if hasattr(v, "synthesize_wav"):
            v.synthesize_wav(text, wf)
        else:
            v.synthesize(text, wf)
    hz = int(re.sub(r"[^\d-]", "", pitch or "0") or 0)
    k = 1 + hz / 150  # +/- Hz -> facteur de hauteur approximatif
    sr = v.config.sample_rate
    af = f"asetrate={sr}*{k:.3f},aresample=24000,atempo={1 / k:.4f}" if hz else "aresample=24000"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-af", af, "-q:a", "3", str(out)],
                   check=True)
    wav.unlink(missing_ok=True)


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
        voice = sc.get("voice") or config.VOICE
        if not config.OFFLINE:
            for attempt in range(3):
                try:
                    words = asyncio.run(asyncio.wait_for(
                        _edge(text, mp3, voice, sc.get("rate", ""), sc.get("pitch", "")), timeout=60))
                    if mp3.exists() and mp3.stat().st_size > 1000:
                        break
                    words = None
                except Exception as e:
                    print(f"[voix] Edge TTS essai {attempt + 1} : {e}")
            if words is None:
                try:
                    _piper(text, mp3, voice, sc.get("pitch", ""))
                    words = []
                    print("[voix] voix de secours Piper utilisée")
                except Exception as e:
                    print(f"[voix] Piper indisponible ({e}), voix muette de secours")
        if words is None:
            est = max(1.5, len(text.split()) / 2.7)
            _silent(est, mp3)
            words = []
        dur = _probe_duration(mp3)
        if not words:
            words = _estimate_words(text, dur)
        sc.update(audio=str(mp3), duration=dur + 0.15, words=_align_punctuation(text, words))
    return scenes
