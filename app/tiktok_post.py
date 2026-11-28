"""Dépôt automatique de la vidéo sur TikTok en PRIVÉ (« Moi uniquement ») via l'API officielle
Content Posting (gratuite). L'utilisateur valide en passant la vidéo en public depuis l'appli TikTok.

Secrets GitHub nécessaires : TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN.
Le nouveau jeton de rafraîchissement renvoyé par TikTok est écrit dans un fichier temporaire
(jamais dans le dépôt) pour que le workflow mette à jour le secret.
"""
import json
import math
import os
import time
from pathlib import Path

import requests

API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024


def configured() -> bool:
    return all(os.getenv(k) for k in ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REFRESH_TOKEN"))


def _token_request(data: dict) -> dict:
    data = {"client_key": os.environ["TIKTOK_CLIENT_KEY"],
            "client_secret": os.environ["TIKTOK_CLIENT_SECRET"], **data}
    r = requests.post(f"{API}/oauth/token/", data=data, timeout=60,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError(f"TikTok a refusé le jeton : {j.get('error')} {j.get('error_description', '')}")
    return j


def save_refresh(token: str):
    """Écrit le jeton hors du dépôt, pour que le workflow le range dans les secrets chiffrés."""
    dest = os.getenv("TIKTOK_TOKEN_OUT")
    if dest and token:
        Path(dest).write_text(token)


def exchange_code(code: str, redirect_uri: str) -> dict:
    j = _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri})
    save_refresh(j.get("refresh_token", ""))
    return {"open_id": j.get("open_id"), "scope": j.get("scope")}


def access_token() -> str:
    j = _token_request({"grant_type": "refresh_token", "refresh_token": os.environ["TIKTOK_REFRESH_TOKEN"]})
    save_refresh(j.get("refresh_token", ""))
    return j["access_token"]


def _post(tok: str, path: str, body: dict) -> dict:
    r = requests.post(f"{API}{path}", json=body, timeout=60, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"})
    j = r.json()
    err = j.get("error", {})
    if err.get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok {path} : {err.get('code')} {err.get('message', '')}")
    return j.get("data", {})


def creator_info(tok: str) -> dict:
    return _post(tok, "/post/publish/creator_info/query/", {})


def post_private(video: Path, caption: str) -> dict:
    """Envoie la vidéo et la publie en privé. Retourne {status, publish_id, account}."""
    tok = access_token()
    info = creator_info(tok)
    size = video.stat().st_size
    if size <= CHUNK:
        chunk, count = size, 1
    else:
        chunk, count = CHUNK, size // CHUNK  # le dernier morceau absorbe le reste
    post_info = {"title": caption[:2200], "privacy_level": "SELF_ONLY",
                 "disable_comment": False, "disable_duet": False, "disable_stitch": False,
                 "is_aigc": True}
    body = {"post_info": post_info,
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": chunk, "total_chunk_count": count}}
    try:
        data = _post(tok, "/post/publish/video/init/", body)
    except RuntimeError as e:
        if "is_aigc" not in str(e) and "invalid_params" not in str(e):
            raise
        post_info.pop("is_aigc")
        data = _post(tok, "/post/publish/video/init/", body)
    pid, url = data["publish_id"], data["upload_url"]
    with open(video, "rb") as f:
        for i in range(count):
            start = i * chunk
            end = size - 1 if i == count - 1 else start + chunk - 1
            f.seek(start)
            part = f.read(end - start + 1)
            r = requests.put(url, data=part, timeout=600, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(part)),
                "Content-Range": f"bytes {start}-{end}/{size}"})
            if r.status_code not in (200, 201, 206):
                raise RuntimeError(f"Envoi du morceau {i + 1}/{count} refusé ({r.status_code}) : {r.text[:300]}")
    status = "PROCESSING_UPLOAD"
    for _ in range(60):
        time.sleep(10)
        st = _post(tok, "/post/publish/status/fetch/", {"publish_id": pid})
        status = st.get("status", status)
        if status in ("PUBLISH_COMPLETE", "FAILED", "SEND_TO_USER_INBOX"):
            if status == "FAILED":
                raise RuntimeError(f"TikTok a refusé la publication : {st.get('fail_reason')}")
            break
    return {"status": status, "publish_id": pid, "account": info.get("creator_username"),
            "privacy_options": info.get("privacy_level_options")}


if __name__ == "__main__":  # échange du code d'autorisation (workflow « Connexion TikTok »)
    print(json.dumps(exchange_code(os.environ["TIKTOK_CODE"], os.environ["TIKTOK_REDIRECT_URI"])))
