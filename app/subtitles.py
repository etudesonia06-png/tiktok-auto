"""Sous-titres dynamiques style TikTok (ASS) : 3 mots max, mot prononcé surligné,
accroche en haut au début, mots forts au centre."""
import re
from pathlib import Path

from . import config

FONT = "Montserrat"


def _ts(t: float) -> str:
    t = max(0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


EMOJI = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200D]")


def _esc(s: str) -> str:
    s = EMOJI.sub("", s).strip()
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


HEADER = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {config.WIDTH}
PlayResY: {config.HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT},86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,2,70,70,560,1
Style: Hook,{FONT},92,&H00FFFFFF,&H00FFFFFF,&H00000000,&HC0000000,-1,0,0,0,100,100,0,0,3,26,0,8,60,60,260,1
Style: Big,{FONT},118,&H0000E5FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,2,0,1,9,4,5,60,60,0,1
Style: Credit,{FONT},30,&H99FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,3,30,30,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

HIGHLIGHT = r"{\c&H0000E5FF&\fscx108\fscy108}"   # jaune TikTok
NORMAL = r"{\c&H00FFFFFF&\fscx100\fscy100}"


def build(script: dict, scenes: list[dict], dest: Path, credit: str = "") -> Path:
    lines = [HEADER]
    offset = 0.0
    # accroche
    lines.append(f"Dialogue: 2,{_ts(0)},{_ts(2.6)},Hook,,0,0,0,,"
                 r"{\fad(120,200)\t(0,180,\fscx110\fscy110)\t(180,320,\fscx100\fscy100)}"
                 f"{_esc(script.get('hook', '')).upper()}")
    for sc in scenes:
        words = sc["words"]
        # groupes de 3 mots, coupés sur la ponctuation
        groups, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) == 3 or w[2][-1:] in ".,!?;:…":
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        for gi, g in enumerate(groups):
            g_end = groups[gi + 1][0][0] if gi + 1 < len(groups) else sc["duration"]
            for wi, (ws, we, _) in enumerate(g):
                st = ws
                en = g[wi + 1][0] if wi + 1 < len(g) else g_end
                parts = []
                for k, (_, _, txt) in enumerate(g):
                    parts.append((HIGHLIGHT if k == wi else NORMAL) + _esc(txt).upper())
                pop = r"{\fad(40,0)}" if wi == 0 else ""
                lines.append(f"Dialogue: 1,{_ts(offset + st)},{_ts(offset + en)},Sub,,0,0,0,,"
                             f"{pop}{' '.join(parts)}")
        if sc.get("onscreen"):
            # au-dessus des têtes (ne masque pas les visages en gros plan), après l'accroche
            s0 = offset + (2.7 if offset < 2.7 else 0.05)
            s1 = min(offset + sc["duration"], s0 + 2.2)
            if s1 - s0 > 0.8:
                lines.append(f"Dialogue: 0,{_ts(s0)},{_ts(s1)},Big,,0,0,0,,"
                             r"{\an5\pos(540,400)\fad(80,150)\t(0,150,\fscx115\fscy115)\t(150,300,\fscx100\fscy100)}"
                             f"{_esc(sc['onscreen']).upper()}")
        offset += sc["duration"]
    if credit:
        lines.append(f"Dialogue: 0,{_ts(0)},{_ts(offset)},Credit,,0,0,0,,{_esc(credit)}")
    dest.write_text("\n".join(lines), encoding="utf-8")
    return dest


def build_srt(scenes: list[dict], dest: Path) -> Path:
    out, n, offset = [], 1, 0.0

    def srt_ts(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for sc in scenes:
        w = sc["words"]
        for i in range(0, len(w), 6):
            chunk = w[i:i + 6]
            out.append(f"{n}\n{srt_ts(offset + chunk[0][0])} --> {srt_ts(offset + chunk[-1][1])}\n"
                       + " ".join(x[2] for x in chunk) + "\n")
            n += 1
        offset += sc["duration"]
    dest.write_text("\n".join(out), encoding="utf-8")
    return dest
