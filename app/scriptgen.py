"""Choix du sujet + écriture du script avec Gemini (offre gratuite)."""
import json
import time
import re
from datetime import date

import requests

from . import config

SCHEMA_HINT = """Réponds UNIQUEMENT avec un JSON valide de cette forme :
{
  "topic": "sujet choisi",
  "title": "titre court (max 6 mots)",
  "hook": "texte affiché à l'écran pendant les 2 premières secondes (max 7 mots)",
  "setting": "décor principal : stadium (stade), apartment (petit appartement parisien), street (rue de Paris la nuit)",
  "cast": [{"id": "un id parmi : lion, supporter_rouge, supporter_vert, supporter_bleu, yanis, nadia, amar, sofiane", "colors": ["#hex maillot", "#hex bande"]}],
  "scenes": [
    {"speaker": "id du personnage qui parle", "narration": "réplique dite par ce personnage (ou narration)", "visual": "mots-clés EN ANGLAIS (secours)", "onscreen": "1 à 4 mots forts affichés en gros (optionnel)"}
  ],
  "description": "description TikTok (1 à 2 phrases, avec une question pour faire commenter)",
  "hashtags": ["#exemple", "..."],
  "cta": "appel à l'action final parlé (s'abonner / commenter)",
  "best_time": "HH:MM heure de Paris conseillée pour publier"
}"""


def _prompt(mode: str, candidates: list[dict], history: list[dict], insights: str) -> str:
    recent = ", ".join(h.get("topic", "") for h in history[-14:]) or "aucun"
    words_min, words_max = word_range()
    base = f"""Tu es un scénariste TikTok francophone expert en vidéos virales et respectueuses des règles de TikTok.
Écris une vidéo verticale ORIGINALE en français, durée parlée {config.TARGET_SECONDS[0]}-{config.TARGET_SECONDS[1]} secondes.
IMPÉRATIF DE LONGUEUR : entre {words_min} et {words_max} mots de narration AU TOTAL (compte-les), en 10 à 14 scènes
de 14 à 24 mots chacune. Un script trop court est refusé.
Personnages 3D disponibles (2 à 3 par vidéo) : lion (mascotte du compte, drôle et chambreur, voix grave),
supporter_rouge (supporter fougueux), supporter_vert (supporter barbu, rapide et moqueur),
supporter_bleu (une supportrice, maligne et ironique) ; adapte leurs "colors" aux équipes du sujet (codes hex).
Pour la série : yanis (24 ans), nadia (sa mère, porte un foulard), amar (son père, moustache),
sofiane (son cousin, casquette, blagueur).
Chaque scène est une réplique d'UN personnage ("speaker") ; écris des dialogues vivants qui s'enchaînent.
Règles :
- Phrase d'accroche choc dans la 1re scène (curiosité, chiffre, promesse), compréhensible sans le son.
- Phrases courtes, langage parlé naturel, tutoiement, rythme rapide, une relance toutes les 10 secondes.
- Aucune fausse information, aucun contenu choquant, politique clivant ou trompeur. Pas de marque déposée.
- Terminer par un appel à l'action naturel (s'abonner pour la suite / commenter).
- 3 à 5 hashtags pertinents en français, dont 1 large (#pourtoi ou #fyp).
Sujets déjà traités récemment (à éviter) : {recent}
Ce qui a le mieux marché jusqu'ici : {insights or "pas encore de données"}
"""
    if mode == "series":
        base += f"""
Format : ÉPISODE COURT de la série « {config.SERIES_NAME} ».
Contexte : {config.SERIES_CONTEXT}
Raconte un moment fort et précis de la vie de Yanis, en dialogues entre les personnages (et un peu de narration),
avec une fin en suspens qui donne envie de voir la suite. Si une tendance du jour ci-dessous (fête, météo, sport,
événement léger) peut s'intégrer naturellement à l'épisode, utilise-la pour qu'il colle à l'actualité.
Décor ("setting") : apartment ou street. Les visuels doivent évoquer Paris, la vie étudiante,
l'Algérie (Béjaïa, la mer, la famille) avec des mots-clés en anglais génériques (ex: "young man paris street night").
Tendances du jour :
{_fmt(candidates, 15)}
"""
    elif mode == "football":
        sport = [c for c in candidates if c.get("source") == "sport"]
        cands = _fmt(sport + [c for c in candidates if c not in sport], 25)
        base += f"""
Format : SKETCH HUMORISTIQUE FOOT en animation 3D pour le compte {config.ACCOUNT}.
Contexte : {config.FOOTBALL_CONTEXT}
Pars de l'actualité foot du jour si un sujet s'y prête (tendances ci-dessous), sinon d'une situation que tout
supporter connaît. EXCEPTION : si un sujet NON foot de la liste est nettement le plus viral du jour (gros volume,
sujet léger et rassembleur), traite-le plutôt en sketch humoristique 3D avec les mêmes personnages. Dialogues courts et drôles entre 2 ou 3 personnages, chute finale inattendue,
question finale qui pousse à commenter (« Et toi, tu soutiens qui ? »). Visuels : mots-clés anglais génériques
(ex: "football stadium crowd night", "soccer fans celebrating"). Décor ("setting") : stadium.
Tendances du jour (actualité sport en priorité) :
{cands}
"""
    else:
        cands = _fmt(candidates, 30)
        base += f"""
Format : vidéo INFO / ASTUCES / STORYTELLING sur le sujet le plus prometteur pour un public francophone 16-35 ans,
jouée par les personnages 3D (le lion présente, les supporters réagissent). Décor ("setting") : street ou apartment.
Choisis UN sujet parmi ces candidats (tendances Google France du jour + sujets evergreen) ; privilégie
ce qui permet une vidéo utile, surprenante ou émouvante, et évite les faits divers tragiques :
{cands}
"""
    return base + "\n" + SCHEMA_HINT


def word_range() -> tuple[int, int]:
    wps = config.WORDS_PER_SECOND
    return int(config.TARGET_SECONDS[0] * wps * 1.08), int(config.TARGET_SECONDS[1] * wps * 0.92)


def _fmt(cands: list[dict], n: int) -> str:
    return "\n".join(f"- {c['topic']} ({c.get('traffic', '')}) {' | '.join(c.get('news', []))}".rstrip()
                     for c in cands[:n]) or "- (aucune tendance disponible aujourd'hui)"


def word_count(s: dict) -> int:
    return sum(len(sc.get("narration", "").split()) for sc in s.get("scenes", []))


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])


def _call_gemini(prompt: str) -> dict:
    """Essaie chaque modèle ; la clé passe dans un en-tête (jamais dans l'URL ni les journaux)."""
    import time
    last_err = None
    for model in config.GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for wait in (0, 20):
            time.sleep(wait)
            try:
                r = requests.post(url, headers={"x-goog-api-key": config.GEMINI_API_KEY}, timeout=120, json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.95, "responseMimeType": "application/json",
                                         "maxOutputTokens": 8192},
                })
                if r.status_code != 200:
                    try:
                        msg = r.json().get("error", {}).get("message", "")[:200]
                    except Exception:
                        msg = r.text[:200]
                    raise RuntimeError(f"HTTP {r.status_code} {msg}")
                cand = r.json()["candidates"][0]
                text = "".join(p.get("text", "") for p in cand["content"]["parts"] if not p.get("thought"))
                return _parse_json(text)
            except Exception as e:
                last_err = e
                print(f"[script] modèle {model} : {e}")
                if "HTTP 429" not in str(e) and "HTTP 503" not in str(e):
                    break  # inutile de réessayer ce modèle
    raise RuntimeError(f"Gemini indisponible : {last_err}")


def _openai_like(url: str, headers: dict, model: str, prompt: str) -> dict:
    r = requests.post(url, headers=headers, timeout=180, json={
        "model": model, "temperature": 0.95,
        "messages": [{"role": "system", "content": "Tu réponds uniquement avec un objet JSON valide."},
                     {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}})
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} {r.text[:200]}")
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError(f"réponse inattendue : {r.text[:160]!r}")
    return _parse_json(content)


GITHUB_ENDPOINTS = ("https://models.github.ai/inference/chat/completions",)


def _call_github_models(prompt: str) -> dict:
    last = None
    for url in GITHUB_ENDPOINTS:
        for model in config.GITHUB_MODELS:
            m = model.split("/", 1)[1] if "azure" in url and "/" in model else model
            try:
                return _openai_like(url, {"Authorization": f"Bearer {config.GITHUB_TOKEN}",
                                          "Content-Type": "application/json"}, m, prompt)
            except Exception as e:
                last = e
                print(f"[script] GitHub Models {m} : {e}")
    raise RuntimeError(f"GitHub Models indisponible : {last}")


def _call_pollinations(prompt: str) -> dict:
    """Relais gratuit limité à une réponse toutes les 45 s : on attend puis on réessaie."""
    for attempt in range(3):
        try:
            return _openai_like("https://text.pollinations.ai/openai", {}, "openai", prompt)
        except RuntimeError as e:
            if "402" not in str(e) and "429" not in str(e) or attempt == 2:
                raise
            print("[script] Pollinations : limite gratuite, nouvel essai dans 50 s")
            time.sleep(50)


def providers() -> list[tuple[str, callable]]:
    """Fournisseurs de texte gratuits, dans l'ordre de préférence."""
    out = []
    if config.GEMINI_API_KEY:
        out.append(("Gemini", _call_gemini))
    out.append(("Pollinations", _call_pollinations))
    if config.GITHUB_TOKEN:
        out.append(("GitHub Models", _call_github_models))
    return out


def _call_llm(prompt: str) -> tuple[dict, str]:
    last = None
    for name, fn in providers():
        try:
            return fn(prompt), name
        except Exception as e:
            last = e
            print(f"[script] {name} indisponible : {e}")
    raise RuntimeError(f"aucun fournisseur de texte disponible : {last}")


def _validate(s: dict) -> dict:
    scenes = [sc for sc in s.get("scenes", []) if sc.get("narration", "").strip()]
    if len(scenes) < 4:
        raise ValueError("script trop court")
    s["scenes"] = scenes
    if s.get("cta") and s["cta"] not in scenes[-1]["narration"]:
        scenes.append({"narration": s["cta"], "visual": scenes[-1].get("visual", "smiling young man"),
                       "onscreen": "ABONNE-TOI"})
    tags = [t if t.startswith("#") else "#" + t for t in s.get("hashtags", [])][:5]
    s["hashtags"] = tags or ["#pourtoi"]
    s.setdefault("title", s.get("topic", "Vidéo du jour"))
    s.setdefault("hook", s["title"])
    s.setdefault("description", s["title"])
    s.setdefault("best_time", "19:00")
    if s.get("setting") not in ("stadium", "apartment", "street"):
        s["setting"] = {"series": "apartment", "trend": "street"}.get(s.get("mode"), "stadium")
    return s


def _sc(speaker, narration, onscreen=""):
    return {"speaker": speaker, "narration": narration, "onscreen": onscreen}


DEMOS_FOOT = [
    {
        "topic": "Le supporter qui ne veut jamais perdre", "title": "Le pari du lion",
        "hook": "Il a parié sa crinière 😳", "setting": "stadium",
        "cast": [{"id": "supporter_rouge"}, {"id": "lion"}, {"id": "supporter_vert"}],
        "scenes": [
            _sc("supporter_rouge", "Écoute-moi bien, ce soir on gagne trois à zéro. Je te le garantis, sur la tête de ma grand-mère.", "3-0 ?!"),
            _sc("supporter_vert", "Trois à zéro ? Mon frère, la dernière fois tu disais ça, vous avez encaissé un but au bout de cinq minutes.", "5 MINUTES 😂"),
            _sc("supporter_rouge", "C'était un accident ! Le gardien avait le soleil dans les yeux. À vingt et une heures. En décembre.", "LE SOLEIL ?"),
            _sc("lion", "Calmez-vous tous les deux. Moi, je suis neutre. Je suis juste là pour les chips et l'ambiance.", "NEUTRE ?"),
            _sc("supporter_vert", "Neutre ? Tu as les couleurs des deux équipes sur ton maillot, et une écharpe de chaque côté !", "DEUX ÉCHARPES"),
            _sc("lion", "Exactement. Comme ça, quoi qu'il arrive à la fin du match, c'est toujours moi qui gagne.", "LE CERVEAU 🧠"),
            _sc("supporter_rouge", "D'accord, monsieur le génie. Alors on fait un vrai pari. Si mon équipe gagne, tu te rases la crinière.", "LE PARI"),
            _sc("supporter_vert", "Et si c'est mon équipe qui gagne, tu portes un bonnet de grand-mère au prochain match. Devant tout le stade.", "LE BONNET 🧶"),
            _sc("lion", "Pari accepté. Mais si c'est match nul, vous m'invitez au restaurant tous les deux. Entrée, plat, dessert.", "MATCH NUL ?"),
            _sc("supporter_rouge", "Match nul ? Ça n'arrive jamais entre nous. Marché conclu ! Tope là, crinière de luxe.", "TOPE LÀ ✋"),
            _sc("supporter_vert", "Quatre-vingt-dixième minute, toujours zéro partout… L'arbitre regarde sa montre… Il siffle !", "COUP DE SIFFLET"),
            _sc("lion", "Zéro à zéro ! Bon, les amis, j'ai très faim. Je prendrai le menu le plus cher, avec deux desserts.", "0-0 🦁"),
            _sc("lion", "Et toi, tu aurais parié sur qui ? Dis-le en commentaire, et abonne-toi pour voir l'addition au restaurant !", "ABONNE-TOI"),
        ],
        "description": "Il est trop fort ce lion 😂 Et toi, tu aurais parié sur qui ? 👇",
        "hashtags": ["#pourtoi", "#football", "#humour", "#supporters", "#animation3d"],
    },
    {
        "topic": "Le supporter qui commente tout depuis son canapé", "title": "L'entraîneur du canapé",
        "hook": "Il n'a jamais joué… mais il sait tout 😂", "setting": "stadium",
        "cast": [{"id": "supporter_bleu"}, {"id": "lion"}, {"id": "supporter_rouge"}],
        "scenes": [
            _sc("supporter_bleu", "Non mais regarde-le ! Pourquoi il fait la passe en arrière ? Moi, à sa place, je tire direct !", "TIRE !!"),
            _sc("lion", "Toi, tirer ? La semaine dernière, tu as raté la poubelle avec une canette. À un mètre.", "À UN MÈTRE 😭"),
            _sc("supporter_bleu", "Ça n'a rien à voir. La canette avait un effet bizarre. Et puis il y avait du vent dans le salon.", "DU VENT ?"),
            _sc("supporter_rouge", "Il y a toujours une excuse avec lui. Le vent, le soleil, la pelouse, ses chaussettes trop serrées.", "LES EXCUSES"),
            _sc("supporter_bleu", "Bon, regardez bien. Si l'entraîneur m'écoutait, on passerait en quatre-trois-trois, avec trois attaquants.", "4-3-3"),
            _sc("lion", "On joue déjà en quatre-trois-trois. Ça fait deux ans. Tu le dis à chaque match.", "DEPUIS 2 ANS"),
            _sc("supporter_bleu", "Alors en cinq-cinq-zéro ! Tout le monde attaque, tout le monde défend. Personne ne s'y attend.", "5-5-0 🤯"),
            _sc("supporter_rouge", "Ça fait dix joueurs plus le gardien… Attends… En fait, ça marche. Comment ça marche ?", "ÇA MARCHE ?!"),
            _sc("lion", "Ça ne marche pas. Ça s'appelle courir partout comme des poules. Même à la récré on ne fait pas ça.", "LES POULES 🐔"),
            _sc("supporter_bleu", "Rigolez. Un jour, un grand club va m'appeler. Et ce jour-là, vous demanderez des places gratuites.", "UN JOUR…"),
            _sc("supporter_rouge", "Ton téléphone sonne, là ! C'est peut-être le grand club !", "📱 DRING"),
            _sc("lion", "C'est ta mère. Elle demande pourquoi tu cries contre la télé à minuit.", "C'EST MAMAN 😂"),
            _sc("lion", "Et toi, tu es plutôt entraîneur du canapé ou supporter calme ? Dis-le en commentaire et abonne-toi !", "ET TOI ?"),
        ],
        "description": "On a tous un pote entraîneur du canapé 😂 Tague-le ! 👇",
        "hashtags": ["#pourtoi", "#football", "#humourfoot", "#supporters", "#animation3d"],
    },
]

DEMO_SERIES = {
    "topic": "Le premier mois de Yanis à Paris", "setting": "apartment",
    "cast": [{"id": "nadia"}, {"id": "yanis"}, {"id": "sofiane"}],
    "title": "Son premier mois à Paris", "hook": "Il est arrivé avec 200 € 😳",
    "scenes": [
        _sc("yanis", "Je suis arrivé à Paris avec deux cents euros et une valise pleine de rêves. Et franchement, j'y croyais.", "200 €"),
        _sc("nadia", "Yanis, mon fils, j'ai mis des gâteaux dans chaque poche de ton manteau. Tu manges, d'accord ? Tu ne sautes aucun repas.", "MAMAN ❤️"),
        _sc("yanis", "Oui, maman. Mais le premier soir, j'ai compris une chose : ici, même un petit café en terrasse coûte trois euros.", "3 € LE CAFÉ"),
        _sc("sofiane", "Bienvenue à Paris, cousin ! Et ton studio, alors ? Raconte, il est comment ?", "ET LE STUDIO ?"),
        _sc("yanis", "Six cents euros pour neuf mètres carrés. Quand je tends les bras, je touche les deux murs en même temps.", "9 m²"),
        _sc("sofiane", "Neuf mètres carrés ? Chez nous à Béjaïa, c'est la taille du placard à chaussures de ta mère !", "LE PLACARD 😂"),
        _sc("yanis", "Rigole. Après le loyer, il me reste quarante euros pour tout le mois. Je fais comment, moi ?", "40 € / MOIS"),
        _sc("sofiane", "J'ai une idée complètement folle. Tu livres des repas à vélo, le soir, après les cours.", "UNE IDÉE FOLLE"),
        _sc("yanis", "Alors j'ai pédalé. Quarante kilomètres par soir, sous la pluie, avec les cours le lendemain à huit heures.", "40 KM / JOUR"),
        _sc("nadia", "Tu as l'air fatigué sur la photo, mon fils. Tu dors assez ? Tu as froid là-bas ?", "TU DORS ASSEZ ?"),
        _sc("yanis", "Et puis un soir, une dernière livraison. Un vieux monsieur m'a ouvert la porte et m'a regardé longtemps.", "LA DERNIÈRE LIVRAISON"),
        _sc("yanis", "Il m'a dit : « Tu es étudiant, toi. Entre, j'ai une proposition à te faire. » Et ma vie a changé.", "LA SUITE…"),
    ],
    "description": "Tu aurais tenu combien de temps à sa place ? 👇",
    "hashtags": ["#pourtoi", "#etudiant", "#algerie", "#paris", "#histoirevraie"],
    "cta": "Abonne-toi pour découvrir la suite de l'histoire de Yanis.",
}


def demo_football(i: int = 0) -> dict:
    import copy
    d = copy.deepcopy(DEMOS_FOOT[i % len(DEMOS_FOOT)])
    d.update(best_time="19:00", mode="football", source="secours")
    return _validate(d)


def demo_script(mode: str, i: int = 0) -> dict:
    """Script de secours (tests hors ligne ou panne de Gemini)."""
    import copy
    if mode in ("football", "trend"):
        d = demo_football(i)
        d["mode"] = mode
        return d
    d = copy.deepcopy(DEMO_SERIES)
    d.update(best_time="19:00", mode=mode, source="secours")
    return _validate(d)


def generate(candidates: list[dict], history: list[dict], insights: str = "",
             mode: str | None = None, feedback: str = "") -> dict:
    if mode is None:
        mode = config.SCHEDULE.get(date.today().weekday(), "football")
    if config.OFFLINE:
        print("[script] mode hors ligne : script de secours")
        return demo_script(mode, len(history))
    prompt = _prompt(mode, candidates, history, insights)
    lo, hi = word_range()
    best = None
    for attempt in range(4):
        try:
            raw, source = _call_llm(prompt + ("\n" + feedback if feedback else ""))
            s = _validate(raw)
            s["mode"] = mode
            s["source"] = source
            n = word_count(s)
            print(f"   → essai {attempt + 1} : {n} mots (visé {lo}-{hi})")
            if best is None or abs(n - (lo + hi) / 2) < abs(word_count(best) - (lo + hi) / 2):
                best = s
            if lo <= n <= hi + 15:
                return s
            feedback = (f"ATTENTION : ton script précédent faisait {n} mots. Il en faut entre {lo} et {hi}. "
                        + ("Ajoute des scènes et développe les répliques." if n < lo else "Raccourcis-le."))
        except Exception as e:
            print(f"[script] tentative {attempt + 1} échouée : {e}")
    if best is not None and word_count(best) >= lo * 0.8:
        return best
    print("[script] aucun fournisseur disponible, script de secours")
    return demo_script(mode, len(history))
