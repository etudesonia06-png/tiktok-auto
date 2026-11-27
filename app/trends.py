"""Recherche quotidienne des tendances en France (sources gratuites, sans clé)."""
import re
import xml.etree.ElementTree as ET

import requests

from . import config

GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=FR"

# Thèmes « evergreen » qui marchent bien et collent à l'identité du compte
EVERGREEN = [
    "5 choses que personne ne te dit avant d'étudier en France",
    "Combien coûte vraiment un mois d'étudiant à Paris",
    "Les phrases que toutes les mères algériennes disent",
    "Astuces pour trouver un job étudiant en une semaine",
    "Ce que j'aurais aimé savoir avant d'arriver en France",
    "Les erreurs d'argent qui coûtent cher à 20 ans",
    "3 recettes algériennes à moins de 5 euros",
    "Comment réussir son premier entretien d'embauche",
]

BLOCKLIST = re.compile(
    r"\b(mort|décès|meurtre|attentat|tué|accident|guerre|viol|procès|élection|politique)\b",
    re.I)


def fetch_google_trends(limit: int = 15) -> list[dict]:
    r = requests.get(GOOGLE_TRENDS_RSS, timeout=20,
                     headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        traffic = it.findtext("ht:approx_traffic", default="", namespaces=ns)
        news = [n.findtext("ht:news_item_title", default="", namespaces=ns)
                for n in it.findall("ht:news_item", ns)]
        if title and not BLOCKLIST.search(title + " " + " ".join(news)):
            items.append({"topic": title, "traffic": traffic, "news": news[:2]})
        if len(items) >= limit:
            break
    return items


def get_trends() -> list[dict]:
    """Retourne une liste de sujets candidats (tendances + evergreen)."""
    trends: list[dict] = []
    if not config.OFFLINE:
        try:
            trends = fetch_google_trends()
        except Exception as e:  # le pipeline ne doit jamais s'arrêter pour ça
            print(f"[tendances] Google Trends indisponible : {e}")
    trends += [{"topic": t, "traffic": "evergreen", "news": []} for t in EVERGREEN]
    return trends
