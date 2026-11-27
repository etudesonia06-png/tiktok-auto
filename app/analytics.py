"""Historique des vidéos et statistiques, et apprentissage simple :
on repère les sujets/formats qui performent pour guider le script suivant."""
import json
from pathlib import Path

from . import config

HISTORY = config.DATA_DIR / "history.json"
STATS = config.DATA_DIR / "stats.json"   # rempli avec les vrais chiffres TikTok


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_history() -> list[dict]:
    return _load(HISTORY, [])


def add_history(entry: dict):
    h = load_history()
    h.append(entry)
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(h, ensure_ascii=False, indent=2), encoding="utf-8")


def insights() -> str:
    """Résumé texte des meilleures vidéos (à partir de stats.json) pour Gemini."""
    stats = _load(STATS, {}).get("videos", [])
    if not stats:
        return ""
    def score(v):
        views = max(v.get("views", 0), 1)
        return views * (1 + 3 * (v.get("shares", 0) + v.get("followers_gained", 0)) / views)
    top = sorted(stats, key=score, reverse=True)[:3]
    flop = sorted(stats, key=score)[:2]
    fmt = lambda v: f"« {v.get('title','?')} » ({v.get('views',0)} vues, {v.get('mode','?')}, publié {v.get('posted_at','?')})"
    return ("Meilleures : " + "; ".join(map(fmt, top)) +
            ". Moins bonnes : " + "; ".join(map(fmt, flop)) +
            ". Reprends les points forts des meilleures (sujet, accroche, format).")
