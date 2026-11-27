"""Préparation de la publication + envoi sur le téléphone via un bot Telegram (gratuit).
La publication sur TikTok reste validée par l'utilisateur."""
import json
from pathlib import Path

import requests

from . import config


def caption(script: dict) -> str:
    return f"{script['description']}\n\n{' '.join(script['hashtags'])}"


def write_post(script: dict, video: Path, dest: Path) -> dict:
    post = {
        "video": video.name,
        "title": script["title"],
        "caption": caption(script),
        "best_time": script.get("best_time", "19:00"),
        "mode": script.get("mode"),
        "topic": script.get("topic"),
        "ai_label": True,  # activer « Contenu généré par l'IA » dans TikTok
        "status": "en attente de validation",
    }
    dest.write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    return post


def _chat_id(base: str) -> str:
    """Identifiant Telegram : secret TELEGRAM_CHAT_ID, sinon le dernier message envoyé au bot."""
    if config.TELEGRAM_CHAT_ID:
        return config.TELEGRAM_CHAT_ID
    try:
        upd = requests.get(f"{base}/getUpdates", timeout=30).json().get("result", [])
        for u in reversed(upd):
            msg = u.get("message") or u.get("edited_message") or {}
            if msg.get("chat", {}).get("type") == "private":
                return str(msg["chat"]["id"])
    except Exception as e:
        print(f"[telegram] getUpdates : {e}")
    return ""


def send_telegram(video: Path, post: dict, extra: str = "") -> bool:
    if not config.TELEGRAM_BOT_TOKEN:
        print("[telegram] non configuré, envoi ignoré")
        return False
    base = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}"
    chat = _chat_id(base)
    if not chat:
        print("[telegram] envoie d'abord « Bonjour » à ton bot dans Telegram")
        return False
    text = (f"🎬 Vidéo du jour prête : {post['title']}\n"
            f"⏰ Publier vers {post['best_time']} (heure de Paris)\n\n"
            f"📝 Légende à copier :\n{post['caption']}\n\n"
            "✅ Pour publier : enregistre la vidéo → TikTok → + → Importer → colle la légende → "
            "ajoute un son tendance à faible volume → active « Contenu généré par l'IA ».")
    if extra:
        text += "\n\n" + extra
    try:
        with open(video, "rb") as f:
            r = requests.post(f"{base}/sendVideo", timeout=300, data={
                "chat_id": chat, "supports_streaming": "true",
                "caption": text[:1000]}, files={"video": f})
        r.raise_for_status()
        if len(text) > 1000:
            requests.post(f"{base}/sendMessage", timeout=30,
                          data={"chat_id": chat, "text": text})
        return True
    except Exception as e:
        print(f"[telegram] échec : {e}")
        return False
