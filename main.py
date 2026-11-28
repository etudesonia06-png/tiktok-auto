"""Usine à vidéos TikTok — exécution quotidienne.

    python main.py                 # vidéo du jour (série ou tendance selon le jour)
    python main.py --mode series   # forcer un épisode de la série
    python main.py --mode trend    # forcer un sujet tendance
    python main.py --check         # vérifier Gemini et Telegram sans rien produire
    OFFLINE=1 python main.py       # test sans réseau (voix muette, visuels générés)
"""
import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import (analytics, animation3d, config, music, publish, render, scriptgen, subtitles, tiktok_post,
                 trends, tts, visuals)


def check() -> int:
    print("Vérification de la configuration (aucune valeur secrète n'est affichée)")
    print(f" - Gemini : {'clé présente' if config.GEMINI_API_KEY else 'CLÉ ABSENTE (secret GEMINI_API_KEY)'}")
    if config.GEMINI_API_KEY and not config.OFFLINE:
        try:
            r = scriptgen._call_gemini('Réponds uniquement {"ok": true} en JSON.')
            print(f" - Gemini : réponse OK {r}")
        except Exception as e:
            print(f" - Gemini : ERREUR {e}")
    print(f" - Telegram : {publish.check()}")
    print(f" - Pexels (secours) : {'clé présente' if config.PEXELS_API_KEY else 'absente (facultatif)'}")
    print(f" - Blender : {animation3d.blender_bin() or 'absent (mode images)'}")
    return 0


def fit_duration(script: dict, scenes: list[dict]) -> list[dict]:
    """Au-delà de 90 s, retire des scènes du milieu (jamais l'accroche ni la fin)."""
    hi = config.TARGET_SECONDS[1]
    while sum(s["duration"] for s in scenes) > hi and len(scenes) > 6:
        i = max(range(2, len(scenes) - 2), key=lambda k: scenes[k]["duration"] if not scenes[k].get("onscreen")
                else scenes[k]["duration"] * 0.7)
        print(f"   → scène {i + 1} retirée pour rester sous {hi} s")
        scenes.pop(i)
    script["scenes"] = scenes
    return scenes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["football", "series", "trend"])
    ap.add_argument("--script", help="script JSON déjà écrit (optionnel)")
    ap.add_argument("--music", help="musique libre de droits en fond (optionnel)")
    ap.add_argument("--check", action="store_true", help="vérifie Gemini et Telegram puis s'arrête")
    args = ap.parse_args()
    if args.check:
        return check()

    t0 = time.time()
    now = datetime.now(ZoneInfo("Europe/Paris"))
    slug = now.strftime("%Y-%m-%d")
    out = config.OUT_DIR / slug
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    print("1/6 Tendances du jour…")
    cands = trends.get_trends()
    history = analytics.load_history()
    lo, hi = config.TARGET_SECONDS
    feedback = ""
    for attempt in range(3):
        print("2/6 Script…")
        if args.script:
            script = scriptgen._validate(json.loads(Path(args.script).read_text(encoding="utf-8")))
        else:
            script = scriptgen.generate(cands, history, analytics.insights(), args.mode, feedback)
        print(f"   → {script['title']} ({script.get('mode')}, {len(script['scenes'])} scènes, "
              f"{scriptgen.word_count(script)} mots, décor {script.get('setting')})")
        cast = animation3d.prepare_cast(script)  # orateur + voix par scène
        print("3/6 Voix off…")
        scenes = tts.synthesize(script["scenes"], work)
        total = sum(s["duration"] for s in scenes)
        print(f"   → durée {total:.1f} s")
        if total >= lo or args.script or config.OFFLINE or not config.GEMINI_API_KEY:
            break
        words = scriptgen.word_count(script)
        need = int(words * (lo + 8) / max(total, 1))
        feedback = (f"ATTENTION : ton script précédent ne durait que {total:.0f} secondes ({words} mots). "
                    f"Écris-en un autre d'au moins {need} mots (vise {lo + 8} secondes).")
        print(f"   ⚠️ trop court, nouveau script demandé ({need} mots visés)")
    scenes = fit_duration(script, scenes)
    total = sum(s["duration"] for s in scenes)
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")

    use3d = config.ENGINE == "blender" and animation3d.blender_bin() is not None
    track, engine = None, "images"
    if use3d:
        print("4/6 Animation 3D (Blender)…")
        try:
            track = animation3d.render(script, scenes, cast, work)
            engine = "3d"
        except Exception as e:
            print(f"   ⚠️ 3D indisponible, passage en mode images : {e}")
    if track is None:
        print("4/6 Images et séquences…")
        scenes = visuals.fetch_all(scenes, work)
    print("5/6 Sous-titres, sons et montage…")
    sfx = animation3d.soundscape(scenes, script.get("mode", "football"), work / "sfx.wav")
    ass = subtitles.build(script, scenes, work / "subs.ass")
    subtitles.build_srt(scenes, out / "sous-titres.srt")
    video = out / f"tiktok_{slug}.mp4"
    bgm = Path(args.music) if args.music else None
    if bgm is None and os.getenv("MUSIC", "1") == "1":
        bgm = music.make(total + 1, script.get("mode", "football"), work / "music.wav", seed=len(history))
    render.render(scenes, ass, video, work, bgm, video=track, sfx=sfx)
    script["engine"] = engine

    print("6/6 Publication préparée…")
    post = publish.write_post(script, video, out / "publication.json")
    warn = ""
    if total < lo:
        warn = f"⚠️ Vidéo de {total:.0f} s : plus courte que prévu ({lo}-{hi} s)."
    # Dépôt TikTok en PRIVÉ : uniquement si explicitement activé (TIKTOK_PRIVATE_UPLOAD=1).
    # Rien n'est jamais rendu public sans ta validation.
    tk = {"status": "désactivé (publication manuelle après validation)"}
    if os.getenv("TIKTOK_PRIVATE_UPLOAD", "0") == "1" and tiktok_post.configured():
        print("   → dépôt en PRIVÉ sur TikTok…")
        try:
            tk = tiktok_post.post_private(video, post["caption"])
            print(f"   → TikTok : {tk['status']} (compte {tk.get('account')})")
        except Exception as e:
            tk = {"status": f"échec : {e}"}
            print(f"   ⚠️ TikTok : {e}")
    post["tiktok"] = tk
    (out / "publication.json").write_text(json.dumps(post, ensure_ascii=False, indent=2), encoding="utf-8")
    if tk["status"] in ("PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"):
        warn = ("✅ Déposée en PRIVÉ sur ton compte TikTok. Pour valider : TikTok → Profil → "
                "la vidéo (cadenas) → ⋯ → Paramètres de confidentialité → « Tout le monde ».\n" + warn).strip()
    print(f"   → vidéo : {total:.1f} s, {video.stat().st_size / 1e6:.1f} Mo, moteur {engine}")
    sent = publish.send_telegram(video, post, warn)
    print(f"   → Telegram : {'envoyée ✅' if sent else 'NON envoyée ❌'}")
    analytics.add_history({"date": slug, "title": script["title"], "topic": script.get("topic"),
                           "mode": script.get("mode"), "engine": engine, "duration": round(total, 1),
                           "video": str(video.relative_to(config.ROOT)) if video.is_relative_to(config.ROOT) else str(video),
                           "caption": post["caption"], "best_time": post["best_time"],
                           "status": "en attente de validation", "telegram": sent,
                           "tiktok": tk.get("status")})
    shutil.rmtree(work, ignore_errors=True)
    print(f"✅ Terminé en {time.time() - t0:.0f} s : {video}")
    if os.getenv("REQUIRE_TELEGRAM") == "1" and not sent:
        print("❌ La vidéo est prête mais n'a pas pu être envoyée sur Telegram")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
