"""Configuration centrale. Toutes les clés viennent des variables d'environnement
(secrets GitHub). Aucune clé n'est jamais écrite dans le code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(os.getenv("OUT_DIR", ROOT / "output"))
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
FONT_DIR = ROOT / "assets" / "fonts"

# Format TikTok
WIDTH, HEIGHT, FPS = 1080, 1920, 30

# Clés (toutes gratuites)
GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
GEMINI_MODELS = [m.strip() for m in os.getenv(
    "GEMINI_MODELS", "gemini-flash-latest,gemini-2.5-flash,gemini-flash-lite-latest,gemini-2.0-flash"
).split(",") if m.strip()]
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
# Petit état privé conservé entre deux exécutions (cache GitHub Actions, jamais dans le dépôt)
STATE_DIR = Path(os.getenv("STATE_DIR", Path.home() / ".tiktok-state"))
TELEGRAM_MAX_MB = 48  # limite d'envoi des bots Telegram : 50 Mo

# Voix française (Microsoft Edge TTS, gratuite)
VOICE = os.getenv("TTS_VOICE", "fr-FR-HenriNeural")
VOICE_RATE = os.getenv("TTS_RATE", "+8%")

# Ligne éditoriale
SERIES_NAME = "De l'Algérie à la France — La galère et la réussite"
SERIES_CONTEXT = (
    "Série d'animation : Yanis, 24 ans, étudiant de Béjaïa parti à Paris pour ses études ; "
    "Nadia sa mère ; Amar son père ; Sofiane son cousin et meilleur ami. Difficultés "
    "financières, solitude, débrouille, puis réussite. Ton : 70 % émotion et réalisme, 30 % humour."
)
ACCOUNT = "@586ai1"
FOOTBALL_CONTEXT = (
    "Humour football en animation 3D : supporters et mascottes (lion mascotte du compte), rivalités entre "
    "sélections africaines et clubs européens, réactions aux matchs et à l'actualité foot. Personnages "
    "originaux uniquement : jamais de vrais joueurs imités, de logos officiels ni de faux documents officiels."
)
# Planning (0 = lundi) : foot 3D la plupart des jours, série mardi et vendredi, sujet viral le dimanche
SCHEDULE = {0: "football", 1: "series", 2: "football", 3: "football", 4: "series", 5: "football", 6: "trend"}
TARGET_SECONDS = (65, 90)  # durée visée : > 1 minute (éligible au Creator Rewards Program)
WORDS_PER_SECOND = 2.75    # débit moyen mesuré des voix françaises utilisées
OFFLINE = os.getenv("OFFLINE", "0") == "1"
ENGINE = os.getenv("ENGINE", "blender")  # "blender" (personnages 3D) ou "images"
