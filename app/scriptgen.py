"""Choix du sujet + écriture du script avec Gemini (offre gratuite)."""
import json
import re
from datetime import date

import requests

from . import config

SCHEMA_HINT = """Réponds UNIQUEMENT avec un JSON valide de cette forme :
{
  "topic": "sujet choisi",
  "title": "titre court (max 6 mots)",
  "hook": "texte affiché à l'écran pendant les 2 premières secondes (max 7 mots)",
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
    words_min, words_max = int(config.TARGET_SECONDS[0] * 2.6), int(config.TARGET_SECONDS[1] * 2.6)
    base = f"""Tu es un scénariste TikTok francophone expert en vidéos virales et respectueuses des règles de TikTok.
Écris une vidéo verticale ORIGINALE en français, durée parlée {config.TARGET_SECONDS[0]}-{config.TARGET_SECONDS[1]} secondes
(soit {words_min} à {words_max} mots de narration au total), en 7 à 10 scènes.
Personnages 3D disponibles (2 à 3 par vidéo) : lion (mascotte du compte, drôle et chambreur),
supporter_rouge, supporter_vert, supporter_bleu (supporters ; adapte leurs "colors" aux équipes du sujet,
codes hex), et pour la série : yanis, nadia (sa mère), amar (son père), sofiane (son cousin).
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
Raconte un moment fort et précis de la vie de Yanis (narration à la 3e personne, voix de conteur),
avec une fin en suspens qui donne envie de voir la suite. Les visuels doivent évoquer Paris, la vie étudiante,
l'Algérie (Béjaïa, la mer, la famille) avec des mots-clés en anglais génériques (ex: "young man paris street night").
"""
    elif mode == "football":
        cands = "\n".join(f"- {c['topic']} {' | '.join(c.get('news', []))}" for c in candidates[:25])
        base += f"""
Format : SKETCH HUMORISTIQUE FOOT en animation 3D pour le compte {config.ACCOUNT}.
Contexte : {config.FOOTBALL_CONTEXT}
Pars de l'actualité foot du jour si un sujet s'y prête (tendances ci-dessous), sinon d'une situation que tout
supporter connaît. EXCEPTION : si un sujet NON foot de la liste est nettement le plus viral du jour (gros volume,
sujet léger et rassembleur), traite-le plutôt en sketch humoristique 3D avec les mêmes personnages. Dialogues courts et drôles entre 2 ou 3 personnages, chute finale inattendue,
question finale qui pousse à commenter (« Et toi, tu soutiens qui ? »). Visuels : mots-clés anglais génériques
(ex: "football stadium crowd night", "soccer fans celebrating").
Tendances du jour :
{cands}
"""
    else:
        cands = "\n".join(f"- {c['topic']} ({c.get('traffic','')}) {' | '.join(c.get('news', []))}"
                          for c in candidates[:25])
        base += f"""
Format : vidéo INFO / ASTUCES / STORYTELLING sur le sujet le plus prometteur pour un public francophone 16-35 ans.
Choisis UN sujet parmi ces candidats (tendances Google France du jour + sujets evergreen) ; privilégie
ce qui permet une vidéo utile, surprenante ou émouvante, et évite les faits divers tragiques :
{cands}
"""
    return base + "\n" + SCHEMA_HINT


def _call_gemini(prompt: str) -> dict:
    last_err = None
    for model in config.GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            r = requests.post(url, params={"key": config.GEMINI_API_KEY}, timeout=90, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"},
            })
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M)
            return json.loads(text)
        except Exception as e:
            last_err = e
            print(f"[script] modèle {model} indisponible : {e}")
    raise RuntimeError(f"Gemini indisponible : {last_err}")


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
    return s


def demo_football() -> dict:
    return _validate({
        "topic": "Le supporter qui ne veut jamais perdre",
        "title": "Le pari du lion",
        "hook": "Il a parié sa crinière 😳",
        "cast": [{"id": "supporter_rouge"}, {"id": "lion"}, {"id": "supporter_vert"}],
        "scenes": [
            {"speaker": "supporter_rouge", "narration": "Écoute-moi bien, ce soir on gagne trois à zéro. Je te le garantis.", "onscreen": "3-0 ?!"},
            {"speaker": "supporter_vert", "narration": "Trois à zéro ? Mon frère, la dernière fois tu disais ça, vous avez perdu au bout de cinq minutes.", "onscreen": "5 MINUTES 😂"},
            {"speaker": "lion", "narration": "Calmez-vous tous les deux. Moi, je suis neutre. Je suis juste là pour les chips.", "onscreen": "NEUTRE ?"},
            {"speaker": "supporter_rouge", "narration": "Neutre ? Tu as les couleurs des deux équipes sur ton maillot !"},
            {"speaker": "lion", "narration": "Exactement. Comme ça, quoi qu'il arrive, c'est moi qui gagne.", "onscreen": "LE CERVEAU 🧠"},
            {"speaker": "supporter_vert", "narration": "D'accord. Alors on fait un pari. Si mon équipe gagne, tu te rases la crinière.", "onscreen": "LE PARI"},
            {"speaker": "lion", "narration": "Pari accepté. Mais si c'est match nul, vous m'invitez au restaurant tous les deux.", "onscreen": "MATCH NUL ?"},
            {"speaker": "supporter_rouge", "narration": "Marché conclu ! Coup de sifflet final dans trois, deux, un…"},
            {"speaker": "lion", "narration": "Zéro à zéro ! Bon, j'ai faim, on y va ? Abonne-toi pour voir l'addition au restaurant.", "onscreen": "0-0 🦁"},
        ],
        "description": "Il est trop fort ce lion 😂 Et toi, tu aurais parié sur qui ? 👇",
        "hashtags": ["#pourtoi", "#football", "#humour", "#supporters", "#animation3d"],
        "best_time": "19:00",
        "mode": "football",
    })


def demo_script(mode: str) -> dict:
    """Script de secours (tests hors ligne ou panne de Gemini)."""
    if mode in ("football", "trend"):
        return demo_football()
    return _validate({
        "topic": "Le premier mois de Yanis à Paris",
        "cast": [{"id": "nadia"}, {"id": "yanis"}, {"id": "sofiane"}],
        "title": "Son premier mois à Paris",
        "hook": "Il est arrivé avec 200 € 😳",
        "scenes": [
            {"narration": "Yanis est arrivé à Paris avec deux cents euros et une valise pleine de rêves.",
             "visual": "young man suitcase train station", "onscreen": "200 €"},
            {"narration": "Sa mère, Nadia, lui avait glissé des gâteaux dans chaque poche du manteau.",
             "visual": "mother hugging son goodbye", "onscreen": "MAMAN ❤️"},
            {"narration": "Le premier soir, il a compris une chose : à Paris, même l'eau du café se paie.",
             "visual": "paris cafe night rain", "onscreen": "TOUT SE PAIE"},
            {"narration": "Son loyer ? Six cents euros pour neuf mètres carrés. Il pouvait toucher les deux murs en même temps.",
             "visual": "small apartment room window", "onscreen": "9 m²"},
            {"narration": "Alors il a appelé Sofiane, son cousin. Et Sofiane a eu une idée complètement folle.",
             "visual": "young man phone call night city", "onscreen": "UNE IDÉE FOLLE"},
            {"narration": "Livrer des repas à vélo, le soir, après les cours. Quarante kilomètres par jour, sous la pluie.",
             "visual": "bike delivery rider rain city", "onscreen": "40 KM / JOUR"},
            {"narration": "Il rentrait épuisé, mais chaque soir il envoyait une photo souriante à sa mère. Pour qu'elle ne s'inquiète pas.",
             "visual": "tired young man sitting stairs", "onscreen": "IL SOURIT QUAND MÊME"},
            {"narration": "Et puis un jour, un client lui a ouvert la porte. Et ce client allait changer sa vie.",
             "visual": "apartment door opening hallway", "onscreen": "LA SUITE…"},
        ],
        "description": "Tu aurais tenu combien de temps à sa place ? 👇",
        "hashtags": ["#pourtoi", "#etudiant", "#algerie", "#paris", "#histoirevraie"],
        "cta": "Abonne-toi pour découvrir la suite de l'histoire de Yanis.",
        "best_time": "19:00",
        "mode": mode,
    })


def generate(candidates: list[dict], history: list[dict], insights: str = "",
             mode: str | None = None) -> dict:
    if mode is None:
        mode = config.SCHEDULE.get(date.today().weekday(), "football")
    if config.OFFLINE or not config.GEMINI_API_KEY:
        print("[script] mode hors ligne : script de démonstration")
        return demo_script(mode)
    for attempt in range(3):
        try:
            s = _validate(_call_gemini(_prompt(mode, candidates, history, insights)))
            s["mode"] = mode
            return s
        except Exception as e:
            print(f"[script] tentative {attempt + 1} échouée : {e}")
    print("[script] échec Gemini, script de secours")
    return demo_script(mode)
