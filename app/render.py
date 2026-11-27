"""Montage automatique avec FFmpeg : séquences recadrées en 1080x1920, effet Ken Burns
sur les images, voix off, musique optionnelle, sous-titres incrustés."""
import random
import subprocess
from pathlib import Path

from . import config

ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
       "-r", str(config.FPS)]


def _run(cmd: list[str]):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("FFmpeg a échoué :\n" + " ".join(cmd) + "\n" + r.stderr[-3000:])


def _scene_clip(sc: dict, i: int, dest: Path):
    W, H, d = config.WIDTH, config.HEIGHT, sc["duration"]
    look = "eq=brightness=-0.05:saturation=1.12:contrast=1.05,vignette=PI/5"
    if sc["media_type"] == "video":
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
              f"fps={config.FPS},{look}")
        _run(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", sc["media"],
              "-t", f"{d:.3f}", "-vf", vf, "-an", *ENC, str(dest)])
    else:
        rnd = random.Random(i)
        sw, sh = int(W * 1.18), int(H * 1.18)
        dx, dy = rnd.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1)])
        x = f"(iw-ow)/2+{dx}*(iw-ow)/2*(t/{d:.3f}-0.5)*1.6"
        y = f"(ih-oh)/2+{dy}*(ih-oh)/2*(t/{d:.3f}-0.5)*1.6"
        vf = (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,crop={sw}:{sh},"
              f"fps={config.FPS},crop={W}:{H}:x='{x}':y='{y}',setsar=1,{look}")
        _run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", sc["media"],
              "-t", f"{d:.3f}", "-vf", vf, *ENC, str(dest)])


def render(scenes: list[dict], ass: Path, dest: Path, workdir: Path,
           music: Path | None = None, video: Path | None = None, sfx: Path | None = None) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    # 1. piste image : vidéo 3D Blender déjà rendue, sinon une séquence par scène
    if video is None:
        clips = []
        for i, sc in enumerate(scenes):
            c = workdir / f"clip_{i:02d}.mp4"
            _scene_clip(sc, i, c)
            clips.append(c)
        lst = workdir / "clips.txt"
        lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
        video = workdir / "video_noaudio.mp4"
        _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
              "-c", "copy", str(video)])

    # 2. piste voix : chaque scène complétée de silence jusqu'à sa durée exacte
    inputs, filt = [], []
    for i, sc in enumerate(scenes):
        inputs += ["-i", sc["audio"]]
        filt.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,"
                    f"apad,atrim=0:{sc['duration']:.3f}[a{i}]")
    filt.append("".join(f"[a{i}]" for i in range(len(scenes))) +
                f"concat=n={len(scenes)}:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11[voice]")
    voice = workdir / "voice.m4a"
    if sfx and Path(sfx).exists():  # ambiance + effets sonores sous la voix
        k = len(scenes)
        inputs += ["-i", str(sfx)]
        filt[-1] = filt[-1].replace("[voice]", "[v0]")
        filt.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo[fx];"
                    "[v0][fx]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[voice]")
    _run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(filt),
          "-map", "[voice]", "-c:a", "aac", "-b:a", "192k", str(voice)])

    # 3. assemblage final + sous-titres (+ musique de fond optionnelle, très basse)
    fontsdir = str(config.FONT_DIR.resolve())
    ass_arg = str(ass.resolve()).replace(":", r"\:").replace("'", r"\'")
    vf = f"subtitles='{ass_arg}':fontsdir='{fontsdir}'"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(voice)]
    if music and music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                f"[0:v]{vf}[v];[2:a]volume=0.10[m];[1:a][m]amix=inputs=2:duration=first:"
                f"dropout_transition=0[a]", "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", vf, "-map", "0:v", "-map", "1:a"]
    cmd += [*ENC, "-profile:v", "high", "-c:a", "aac", "-b:a", "192k", "-shortest",
            "-movflags", "+faststart", str(dest)]
    _run(cmd)
    return dest
