"""Images et séquences vidéo : 1) vidéos verticales Pexels (gratuites, usage commercial),
2) image IA Pollinations (gratuite, sans clé), 3) visuel généré localement en secours."""
import hashlib
import math
import random
import urllib.parse
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

from . import config

PEXELS_ENDPOINTS = ["https://api.pexels.com/v1/videos/search", "https://api.pexels.com/videos/search"]


def _download(url: str, dest: Path) -> Path:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk)
    return dest


def pexels_video(query: str, min_dur: float, dest: Path, used: set) -> Path | None:
    if not config.PEXELS_API_KEY:
        return None
    for ep in PEXELS_ENDPOINTS:
        try:
            r = requests.get(ep, headers={"Authorization": config.PEXELS_API_KEY}, timeout=30,
                             params={"query": query, "orientation": "portrait", "per_page": 15,
                                     "size": "medium"})
            r.raise_for_status()
            break
        except Exception as e:
            print(f"[visuels] Pexels {ep} : {e}")
    else:
        return None
    for v in r.json().get("videos", []):
        if v["id"] in used or v.get("duration", 0) < min(min_dur, 4):
            continue
        files = [f for f in v.get("video_files", []) if f.get("height", 0) >= 1280
                 and f.get("height", 0) > f.get("width", 0) and f.get("file_type") == "video/mp4"]
        if not files:
            continue
        best = min(files, key=lambda f: abs(f["height"] - 1920))
        used.add(v["id"])
        try:
            return _download(best["link"], dest.with_suffix(".mp4"))
        except Exception as e:
            print(f"[visuels] téléchargement Pexels : {e}")
    return None


def pollinations_image(prompt: str, dest: Path) -> Path | None:
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:6], 16)
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(
        prompt + ", cinematic, vertical composition, high detail, no text") +
        f"?width=1080&height=1920&nologo=true&seed={seed}")
    try:
        p = _download(url, dest.with_suffix(".jpg"))
        Image.open(p).verify()
        return p
    except Exception as e:
        print(f"[visuels] Pollinations : {e}")
        return None


PALETTES = [((20, 24, 60), (233, 69, 96)), ((10, 40, 50), (60, 200, 170)),
            ((40, 20, 60), (250, 170, 60)), ((15, 30, 70), (90, 160, 255)),
            ((50, 15, 30), (255, 120, 90)), ((20, 45, 30), (190, 230, 90))]


def procedural_image(seed_text: str, dest: Path) -> Path:
    """Fond animé-friendly : dégradé + formes lumineuses floues (aucun réseau)."""
    rnd = random.Random(seed_text)
    W, H = int(config.WIDTH * 1.2), int(config.HEIGHT * 1.2)
    a, b = rnd.choice(PALETTES)
    y = np.linspace(0, 1, H)[:, None, None]
    x = np.linspace(0, 1, W)[None, :, None]
    t = np.clip(0.65 * y + 0.35 * x, 0, 1)
    arr = (np.array(a) * (1 - t) + np.array(b) * t).astype(np.uint8)
    img = Image.fromarray(arr)
    glow = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(glow)
    for _ in range(9):
        r = rnd.randint(120, 420)
        cx, cy = rnd.randint(0, W), rnd.randint(0, H)
        col = tuple(min(255, c + rnd.randint(20, 90)) for c in rnd.choice([a, b]))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, glow, 0.45)
    # grain léger
    noise = np.random.default_rng(abs(hash(seed_text)) % 2**32).normal(0, 6, (H, W, 1))
    img = Image.fromarray(np.clip(np.asarray(img) + noise, 0, 255).astype(np.uint8))
    p = dest.with_suffix(".jpg")
    img.save(p, quality=92)
    return p


def fetch_all(scenes: list[dict], workdir: Path) -> list[dict]:
    workdir.mkdir(parents=True, exist_ok=True)
    used: set = set()
    for i, sc in enumerate(scenes):
        q = sc.get("visual") or "city life"
        base = workdir / f"visual_{i:02d}"
        media = None
        if not config.OFFLINE:
            media = pexels_video(q, sc["duration"], base, used) or pollinations_image(q, base)
        if media is None:
            media = procedural_image(q + str(i), base)
        sc["media"] = str(media)
        sc["media_type"] = "video" if str(media).endswith(".mp4") else "image"
    return scenes
