"""Préparation de la publication + envoi sur le téléphone via un bot Telegram (gratuit).
La publication sur TikTok reste validée par l'utilisateur."""
import json
import subprocess
from pathlib import Path

import requests

from . import config

CHAT_FILE = config.STATE_DIR / "telegram_chat_id"


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


# ---------------------------------------------------------------- API Telegram
def _api(method: str, timeout: int = 60, **kw) -> dict:
    """Appel à l'API Telegram ; ne laisse jamais le jeton apparaître dans les journaux."""
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/{method}"
    try:
        r = requests.post(url, timeout=timeout, **kw)
        j = r.json()
    except Exception as e:
        msg = str(e).replace(config.TELEGRAM_BOT_TOKEN, "***")
        return {"ok": False, "description": f"réseau : {msg[:200]}"}
    return j


def _chat_from_updates(updates: list) -> str:
    for u in reversed(updates):
        for k in ("message", "edited_message", "channel_post", "my_chat_member", "callback_query"):
            obj = u.get(k) or {}
            chat = obj.get("chat") or (obj.get("message") or {}).get("chat") or {}
            if chat.get("id"):
                return str(chat["id"])
    return ""


def _chat_id() -> str:
    """Identifiant de conversation : secret TELEGRAM_CHAT_ID, sinon identifiant mémorisé,
    sinon le dernier message envoyé au bot (Telegram ne les garde que 24 h, d'où la mémorisation)."""
    if config.TELEGRAM_CHAT_ID:
        return config.TELEGRAM_CHAT_ID
    try:
        saved = CHAT_FILE.read_text().strip()
        if saved:
            return saved
    except OSError:
        pass
    j = _api("getUpdates", data={"timeout": 0})
    if not j.get("ok") and j.get("error_code") == 409:  # un webhook empêche getUpdates
        print("[telegram] webhook actif : suppression pour lire les messages")
        _api("deleteWebhook", data={"drop_pending_updates": "false"})
        j = _api("getUpdates", data={"timeout": 0})
    if not j.get("ok"):
        print(f"[telegram] getUpdates refusé : {j.get('description')}")
        return ""
    chat = _chat_from_updates(j.get("result", []))
    if chat:
        remember_chat(chat)
    return chat


def remember_chat(chat: str):
    try:
        config.STATE_DIR.mkdir(parents=True, exist_ok=True)
        CHAT_FILE.write_text(chat)
    except OSError as e:
        print(f"[telegram] mémorisation impossible : {e}")


def check() -> str:
    """Diagnostic sans rien envoyer : renvoie un texte lisible."""
    if not config.TELEGRAM_BOT_TOKEN:
        return "jeton absent (secret TELEGRAM_BOT_TOKEN)"
    me = _api("getMe", timeout=20)
    if not me.get("ok"):
        return f"jeton refusé par Telegram : {me.get('description')}"
    chat = _chat_id()
    bot = me["result"].get("username", "?")
    return f"bot @{bot} OK, conversation {'trouvée' if chat else 'INTROUVABLE (envoie « Bonjour » au bot)'}"


def _fit_for_telegram(video: Path) -> Path:
    """Les bots Telegram ne peuvent pas envoyer plus de 50 Mo : copie plus légère si besoin."""
    size_mb = video.stat().st_size / 1e6
    if size_mb <= config.TELEGRAM_MAX_MB:
        return video
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                "default=nw=1:nk=1", str(video)], capture_output=True, text=True).stdout or 90)
    kbps = int((config.TELEGRAM_MAX_MB - 3) * 8000 / dur) - 160
    small = video.with_name(video.stem + "_telegram.mp4")
    print(f"[telegram] vidéo de {size_mb:.0f} Mo : copie à {kbps} kb/s pour l'envoi")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-c:v", "libx264", "-preset", "medium",
                    "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{2 * kbps}k",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
                    str(small)], check=True)
    return small


def send_text(text: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN:
        return False
    chat = _chat_id()
    if not chat:
        return False
    return bool(_api("sendMessage", data={"chat_id": chat, "text": text[:4000]}).get("ok"))


def send_telegram(video: Path, post: dict, extra: str = "") -> bool:
    if not config.TELEGRAM_BOT_TOKEN:
        print("[telegram] non configuré (secret TELEGRAM_BOT_TOKEN absent), envoi ignoré")
        return False
    chat = _chat_id()
    if not chat:
        print("[telegram] aucune conversation trouvée : envoie « Bonjour » à ton bot dans Telegram, "
              "ou ajoute le secret TELEGRAM_CHAT_ID")
        return False
    text = (f"🎬 Vidéo du jour prête : {post['title']}\n"
            f"⏰ Publier vers {post['best_time']} (heure de Paris)\n\n"
            f"📝 Légende à copier :\n{post['caption']}\n\n"
            "✅ Pour publier : enregistre la vidéo → TikTok → + → Importer → colle la légende → "
            "ajoute un son tendance à faible volume → active « Contenu généré par l'IA ».")
    if config.VIDEO_LINK:
        text += f"\n\n🔗 Lien de secours : {config.VIDEO_LINK}"
    if extra:
        text += "\n\n" + extra
    try:
        sendable = _fit_for_telegram(video)
    except Exception as e:
        print(f"[telegram] recompression impossible : {e}")
        sendable = video
    ok = False
    for attempt in range(3):
        with open(sendable, "rb") as f:
            j = _api("sendVideo", timeout=600, files={"video": (video.name, f, "video/mp4")}, data={
                "chat_id": chat, "supports_streaming": "true", "width": config.WIDTH,
                "height": config.HEIGHT, "caption": text[:1000]})
        if j.get("ok"):
            ok = True
            break
        print(f"[telegram] envoi vidéo refusé (essai {attempt + 1}) : {j.get('description')}")
        if j.get("error_code") in (400, 403):  # conversation invalide ou bot bloqué : inutile d'insister
            break
    if not ok:  # au moins prévenir avec le texte
        send_text(text + "\n\n⚠️ La vidéo n'a pas pu être jointe : télécharge-la avec le lien de secours"
                  + (f" ou sur {config.VIDEOS_PAGE}" if config.VIDEOS_PAGE else "") + ".")
        return False
    if len(text) > 1000:
        _api("sendMessage", data={"chat_id": chat, "text": text})
    remember_chat(chat)
    return True
