"""Usine à vidéos TikTok — exécution quotidienne.

    python main.py                 # vidéo du jour (série ou tendance selon le jour)
    python main.py --mode series   # forcer un épisode de la série
    python main.py --mode trend    # forcer un sujet tendance
    OFFLINE=1 python main.py       # test sans réseau (voix muette, visuels générés)
"""
import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app import analytics, animation3d, config, publish, render, scriptgen, subtitles, trends, tts, visuals


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["football", "series", "trend"])
    ap.add_argument("--script", help="script JSON déjà écrit (optionnel)")
    ap.add_argument("--music", help="musique libre de droits en fond (optionnel)")
    args = ap.parse_args()

    t0 = time.time()
    now = datetime.now(ZoneInfo("Europe/Paris"))
    slug = now.strftime("%Y-%m-%d")
    out = config.OUT_DIR / slug
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)

    print("1/6 Tendances…")
    cands = trends.get_trends()
    print("2/6 Script…")
    if args.script:
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        script = scriptgen._validate(script)
    else:
        script = scriptgen.generate(cands, analytics.load_history(), analytics.insights(), args.mode)
    (out / "script.json").write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   → {script['title']} ({script.get('mode')}, {len(script['scenes'])} scènes)")

    use3d = config.ENGINE == "blender" and animation3d.blender_bin() is not None
    cast = animation3d.prepare_cast(script)  # orateur + voix par scène
    print("3/6 Voix off…")
    scenes = tts.synthesize(script["scenes"], work)
    total = sum(s["duration"] for s in scenes)
    print(f"   → durée {total:.1f} s")
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
    render.render(scenes, ass, video, work, Path(args.music) if args.music else None, video=track, sfx=sfx)
    script["engine"] = engine

    print("6/6 Publication préparée…")
    post = publish.write_post(script, video, out / "publication.json")
    warn = ""
    if total < config.TARGET_SECONDS[0]:
        warn = (f"⚠️ Vidéo de {total:.0f} s : moins d'1 minute, elle ne comptera pas "
                "pour le Creator Rewards Program.")
    sent = publish.send_telegram(video, post, warn)
    analytics.add_history({"date": slug, "title": script["title"], "topic": script.get("topic"),
                           "mode": script.get("mode"), "engine": engine, "duration": round(total, 1),
                           "video": str(video.relative_to(config.ROOT)) if video.is_relative_to(config.ROOT) else str(video),
                           "caption": post["caption"], "best_time": post["best_time"],
                           "status": "en attente de validation", "telegram": sent})
    shutil.rmtree(work, ignore_errors=True)
    print(f"✅ Terminé en {time.time() - t0:.0f} s : {video}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
