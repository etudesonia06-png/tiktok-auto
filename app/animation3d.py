"""Côté application : prépare la distribution (personnages réutilisables), les voix par personnage,
l'enveloppe de chaque voix pour la synchro labiale, les plans de caméra, lance Blender,
puis assemble les images en vidéo et crée l'ambiance sonore (foule, sifflet, clameur)."""
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import config

SCENE_SCRIPT = Path(__file__).with_name("blender_scene.py")

# Bibliothèque de personnages réutilisables : apparence (pour Blender) + voix (Edge TTS : voix, débit, hauteur)
LIBRARY = {
    "lion": {"type": "lion", "voice": "fr-FR-HenriNeural", "rate": "+6%", "pitch": "-8Hz",
             "colors": ["#ffffff", "#1fa34a", "#f6c21c", "#d62828"], "height": 1.0},
    "supporter_rouge": {"type": "supporter", "voice": "fr-FR-RemyMultilingualNeural", "rate": "+10%", "pitch": "+0Hz",
                        "colors": ["#c1272d", "#006233"], "skin": "#c68642", "hair": "short", "height": 1.0},
    "supporter_vert": {"type": "supporter", "voice": "fr-FR-HenriNeural", "rate": "+14%", "pitch": "+7Hz",
                       "colors": ["#00853f", "#fdef42"], "skin": "#8d5524", "hair": "beard", "height": 0.95},
    "supporter_bleu": {"type": "supporter", "voice": "fr-FR-DeniseNeural", "rate": "+10%", "pitch": "+0Hz",
                       "colors": ["#1d3c8f", "#ffffff"], "skin": "#f1c27d", "hair": "ponytail", "height": 0.92},
    "yanis": {"type": "person", "voice": "fr-FR-RemyMultilingualNeural", "rate": "+6%", "pitch": "+0Hz",
              "colors": ["#2f5d8a", "#e8e8e8"], "skin": "#e0ac69", "hair": "curly", "height": 1.0},
    "nadia": {"type": "person", "voice": "fr-FR-VivienneMultilingualNeural", "rate": "+0%", "pitch": "-2Hz",
              "colors": ["#7b2d5b", "#f2c94c"], "skin": "#c68642", "hair": "scarf", "height": 0.9},
    "amar": {"type": "person", "voice": "fr-FR-HenriNeural", "rate": "-4%", "pitch": "-10Hz",
             "colors": ["#4a4a4a", "#c9a227"], "skin": "#a0522d", "hair": "grey_moustache", "height": 0.98},
    "sofiane": {"type": "person", "voice": "fr-FR-HenriNeural", "rate": "+12%", "pitch": "+6Hz",
                "colors": ["#1b7f5f", "#ffffff"], "skin": "#8d5524", "hair": "cap", "height": 1.02},
}
DEFAULT_CAST = {"football": ["supporter_rouge", "lion", "supporter_vert"],
                "series": ["nadia", "yanis", "sofiane"],
                "trend": ["supporter_bleu", "lion", "supporter_rouge"]}


def blender_bin() -> str | None:
    b = os.getenv("BLENDER_BIN") or shutil.which("blender")
    return b if b and Path(b).exists() else None


def prepare_cast(script: dict) -> list[dict]:
    """Choisit la distribution et attribue un orateur + une voix à chaque scène."""
    mode = script.get("mode", "football")
    ids = []
    for c in script.get("cast", []):
        cid = str(c.get("id", "")).lower()
        if cid in LIBRARY and cid not in ids:
            ids.append(cid)
    if not ids:
        ids = DEFAULT_CAST.get(mode, DEFAULT_CAST["football"])
    ids = ids[:4]
    cast = []
    for cid in ids:
        c = dict(LIBRARY[cid])
        c["id"] = cid
        over = next((x for x in script.get("cast", []) if str(x.get("id", "")).lower() == cid), {})
        if isinstance(over.get("colors"), list) and len(over["colors"]) >= 2:
            c["colors"] = over["colors"]
        cast.append(c)
    voices = {c["id"]: c["voice"] for c in cast}
    for i, sc in enumerate(script["scenes"]):
        sp = str(sc.get("speaker", "")).lower()
        if sp not in voices:
            sp = ids[i % len(ids)] if mode != "series" else ids[min(1, len(ids) - 1)]
        sc["speaker"] = sp
        sc["voice"] = voices[sp]
        sc["rate"] = LIBRARY[sp].get("rate", "")
        sc["pitch"] = LIBRARY[sp].get("pitch", "")
    return cast


def envelope(audio: str, frames: int, fps: int) -> list[float]:
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", audio, "-f", "s16le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
    hop = 16000 // fps
    out = []
    for f in range(frames):
        seg = x[f * hop:(f + 1) * hop]
        out.append(float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0)
    a = np.array(out)
    if a.max() > 0:
        a = np.clip(a / (np.percentile(a, 95) + 1e-6), 0, 1)
    a = np.convolve(a, [0.25, 0.5, 0.25], mode="same")  # bouche plus douce
    return [round(float(v), 3) for v in a]


def build_spec(script: dict, scenes: list[dict], cast: list[dict], fps: int, w: int, h: int) -> dict:
    total = int(round(sum(s["duration"] for s in scenes) * fps))
    env = {c["id"]: [0.0] * total for c in cast}
    speaker_at = [""] * total
    shots, start = [], 0
    prev = scenes[0]["speaker"]
    for i, sc in enumerate(scenes):
        n = int(round(sc["duration"] * fps))
        n = min(n, total - start)
        e = envelope(sc["audio"], n, fps)
        env[sc["speaker"]][start:start + n] = e
        speaker_at[start:start + n] = [sc["speaker"]] * n
        sp = sc["speaker"]
        if i == 0:
            kinds = ["wide_push"]
        elif i == len(scenes) - 1:
            kinds = ["close", "wide"]
        else:
            kinds = [["close", "medium", "low", "over"][i % 4]]
            if n > 5.5 * fps:  # longue réplique : plan de réaction ou plan à deux au milieu
                kinds += [["reaction", "two", "close"][i % 3]]
        cut = start
        for k, kind in enumerate(kinds):
            end = start + n - 1 if k == len(kinds) - 1 else start + int(n * (0.62 if len(kinds) == 2 else 1))
            listener = prev if prev != sp else next((c["id"] for c in cast if c["id"] != sp), sp)
            shots.append({"start": cut, "end": max(cut, end), "speaker": sp, "listener": listener, "type": kind})
            cut = end + 1
        prev = sp
        start += n
    last_start = total - int(round(scenes[-1]["duration"] * fps))
    cheer = list(range(max(0, last_start), total)) if script.get("mode") == "football" else []
    crowd = [c["colors"][0] for c in cast if c["type"] == "supporter"][:2] or ["#c1272d", "#006233"]
    emph = [int(round(sum(x["duration"] for x in scenes[:i]) * fps)) for i, x in enumerate(scenes) if x.get("onscreen")]
    return {"fps": fps, "width": w, "height": h, "total_frames": total, "cast": cast,
            "setting": script.get("setting") or {"series": "apartment", "trend": "street"}.get(
                script.get("mode"), "stadium"), "emphasis": emph,
            "envelopes": env, "speaker_at": speaker_at, "shots": shots, "cheer_frames": cheer,
            "crowd_colors": crowd + ["#ffffff"], "samples": int(os.getenv("RENDER_SAMPLES", "8")),
            "seed": abs(hash(script.get("title", ""))) % 1000}


# Paliers de qualité, du plus beau au plus rapide : (images/s, largeur, hauteur, échantillons)
QUALITY_LADDER = [(15, 576, 1024, 8), (12, 480, 854, 6), (10, 432, 768, 4), (8, 360, 640, 3)]


def _run_blender(spec: dict, workdir: Path, frames: Path, timeout_s: int):
    spec_path = workdir / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    frames.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([blender_bin(), "-b", "--factory-startup", "-noaudio", "-P", str(SCENE_SCRIPT), "--",
                            str(spec_path), str(frames)], capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Rendu 3D arrêté : plus de {timeout_s // 60} min")
    if r.returncode != 0 or not any(frames.glob("f_*.jpg")):
        raise RuntimeError("Rendu Blender échoué :\n" + (r.stdout[-2000:] + r.stderr[-2000:]))


def render(script: dict, scenes: list[dict], cast: list[dict], workdir: Path) -> Path:
    """Lance Blender et renvoie une vidéo muette 1080x1920, en restant dans le budget de temps."""
    import time
    if not blender_bin():
        raise RuntimeError("Blender introuvable (variable BLENDER_BIN)")
    budget = float(os.getenv("RENDER_BUDGET_MIN", "100")) * 60
    frames = workdir / "frames"
    # --- test de vitesse : 6 images au palier le plus beau ; on mesure l'écart entre la 1re et la
    # dernière image écrites (la construction de la scène n'est pas comptée)
    fps, rw, rh, spp = QUALITY_LADDER[0]
    spec = build_spec(script, scenes, cast, fps, rw, rh)
    spec.update(samples=spp, frame_start=1, frame_end=6)
    t0 = time.time()
    _run_blender(spec, workdir, frames, timeout_s=900)
    elapsed = time.time() - t0
    stamps = sorted(f.stat().st_mtime for f in frames.glob("f_*.jpg"))
    if len(stamps) >= 3:
        per_frame = (stamps[-1] - stamps[0]) / (len(stamps) - 1) * 1.1  # marge de 10 %
        setup = max(0.0, elapsed - per_frame * len(stamps))
    else:
        per_frame, setup = elapsed / 6, 0.0
    shutil.rmtree(frames, ignore_errors=True)
    print(f"   Test de vitesse : {per_frame:.1f} s par image (+ {setup:.0f} s de préparation)")
    # --- choix du palier qui tient dans le budget
    base_cost = rw * rh * spp
    choice = None
    for f, w, h, n in QUALITY_LADDER:
        total = int(round(sum(s["duration"] for s in scenes) * f))
        est = per_frame * (w * h * n) / base_cost * total + setup
        print(f"   Palier {f} i/s {w}x{h} {n} éch. : environ {est / 60:.0f} min")
        if est <= budget:
            choice = (f, w, h, n)
            break
    if choice is None:
        raise RuntimeError("Machine trop lente pour la 3D aujourd'hui : passage au mode secours")
    fps, rw, rh, spp = choice
    spec = build_spec(script, scenes, cast, fps, rw, rh)
    spec["samples"] = spp
    print(f"   Rendu 3D : {spec['total_frames']} images {rw}x{rh} à {fps} i/s, {spp} échantillons")
    _run_blender(spec, workdir, frames, timeout_s=int(budget * 1.4))
    out = workdir / "video_noaudio.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", str(fps), "-i", str(frames / "f_%04d.jpg"),
                    "-vf", f"scale={config.WIDTH}:{config.HEIGHT}:flags=lanczos,fps={config.FPS},"
                           "eq=saturation=1.08:contrast=1.03",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", str(out)],
                   check=True)
    shutil.rmtree(frames, ignore_errors=True)
    return out


# ---------------------------------------------------------------- effets sonores (générés, libres de droits)
def _write_wav(path: Path, x: np.ndarray, sr: int):
    x = np.clip(x, -1, 1)
    st = (np.stack([x, x], axis=1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(st.tobytes())


def soundscape(scenes: list[dict], mode: str, dest: Path, sr: int = 32000) -> Path:
    """Ambiance de stade (bruit filtré qui ondule), sifflet au début, clameur à la fin, petits « swoosh »
    aux changements de plan. Tout est synthétisé : aucun problème de droits."""
    total = sum(s["duration"] for s in scenes)
    n = int(total * sr)
    rng = np.random.default_rng(3)
    t = np.arange(n) / sr
    out = np.zeros(n, dtype=np.float32)
    if mode in ("football", "trend"):
        noise = rng.standard_normal(n).astype(np.float32)
        # bruit « brun » doux (foule lointaine)
        crowd = np.cumsum(noise)
        crowd -= np.convolve(crowd, np.ones(4000) / 4000, mode="same")
        crowd /= np.abs(crowd).max() + 1e-6
        swell = 0.55 + 0.25 * np.sin(2 * np.pi * t / 7.0) + 0.2 * np.sin(2 * np.pi * t / 2.9)
        out += 0.10 * crowd * swell
        # sifflet d'arbitre
        dur = 0.7
        m = t < dur
        trill = 1 + 0.5 * np.sign(np.sin(2 * np.pi * 28 * t[m]))
        out[m] += 0.22 * np.sin(2 * np.pi * 2900 * t[m]) * trill * np.minimum(1, (dur - t[m]) * 8)
        # clameur sur la dernière scène
        last = scenes[-1]["duration"]
        s0 = int((total - last) * sr)
        k = np.arange(n - s0) / sr
        cheer = rng.standard_normal(n - s0) * np.minimum(1, k / 0.6) * np.exp(-np.maximum(0, k - last + 1.2) * 2)
        out[s0:] += 0.12 * cheer.astype(np.float32)
    # swoosh aux changements de plan
    acc = 0.0
    for sc in scenes[:-1]:
        acc += sc["duration"]
        s0, L = int((acc - 0.12) * sr), int(0.25 * sr)
        if 0 <= s0 < n - L:
            win = np.hanning(L)
            sw = rng.standard_normal(L) * win
            sw = np.convolve(sw, np.ones(12) / 12, mode="same")
            out[s0:s0 + L] += 0.18 * sw.astype(np.float32)
    _write_wav(dest, out, sr)
    return dest
