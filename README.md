# Usine à vidéos TikTok

Chaque matin, sans ordinateur allumé, cette application :

1. récupère les tendances du jour en France (Google Trends) et des sujets qui marchent toujours ;
2. choisit le sujet et écrit un script de 61 à 75 s (Gemini, offre gratuite) : épisode de la série
   « De l'Algérie à la France » certains jours, sujet tendance les autres jours ;
3. génère une voix off française naturelle (voix Microsoft Edge, gratuite) ;
4. anime de vrais personnages 3D réutilisables avec Blender (gratuit) : mascotte lion, supporters aux couleurs des équipes,
   personnages de la série ; bouche synchronisée sur la voix, clignements, gestes, stade, caméra plan par plan
   (secours automatique : séquences Pexels ou images IA si le rendu 3D échoue) ;
5. fait le montage : 1080 × 1920, sous-titres dynamiques mot par mot, accroche, mots forts, ambiance de stade,
   sifflet, clameur et transitions sonores (sons synthétisés, libres de droits) ;
6. exporte un MP4 vertical 1080 × 1920 et te l'envoie sur Telegram avec la légende, les hashtags et l'heure de publication conseillée ;
7. garde l'historique et s'appuie sur les statistiques pour améliorer les vidéos suivantes.

Tu n'as plus qu'à regarder la vidéo et à la publier si elle te plaît.

**Coût : 0 €.** Tout tourne sur GitHub Actions. Le rendu 3D prend environ 45 à 90 minutes par vidéo :
utilise un dépôt **public** (minutes illimitées et gratuites ; tes clés restent secrètes). En dépôt privé,
les 2 000 minutes gratuites par mois suffisent à peine, et GitHub met simplement la tâche en pause sans rien facturer.

## Installation (une seule fois, environ 20 minutes)

### 1. Créer les 3 clés gratuites
| Clé | Où | Nom du secret |
|---|---|---|
| Gemini | aistudio.google.com → « Get API key » | `GEMINI_API_KEY` |
| Pexels (facultatif, secours) | pexels.com/api → « Your API key » | `PEXELS_API_KEY` |
| Bot Telegram | Dans Telegram, écris à **@BotFather** → `/newbot` → copie le jeton | `TELEGRAM_BOT_TOKEN` |
| (automatique) | Envoie simplement « Bonjour » à ton bot : l'application trouve ton identifiant seule | `TELEGRAM_CHAT_ID` facultatif |

### 2. Créer le dépôt GitHub
1. Crée un compte sur github.com (gratuit).
2. « New repository », nom `tiktok-auto`, **Private**, puis crée-le.
3. Envoie tous les fichiers de ce dossier dans le dépôt (Claude peut le faire pour toi si tu lui donnes accès au dépôt).

### 3. Ajouter les secrets
Dépôt → **Settings → Secrets and variables → Actions → New repository secret**, puis ajoute les 4 secrets du tableau.

### 4. Lancer un premier test
Dépôt → **Actions → Vidéo TikTok du jour → Run workflow**. Environ 8 minutes plus tard, la vidéo arrive sur Telegram.
Ensuite, elle se lance toute seule chaque matin vers 6 h 17 (heure de Paris).

## Réglages (fichier `app/config.py` ou variables d'environnement)
- `TTS_VOICE` : `fr-FR-HenriNeural` (homme), `fr-FR-DeniseNeural` ou `fr-FR-VivienneMultilingualNeural` (femme).
- `SCHEDULE` (app/config.py) : foot 3D lundi, mercredi, jeudi, samedi ; série mardi et vendredi ; sujet viral le dimanche.
- Musique de fond : ajoute plutôt un son tendance directement dans TikTok au moment de publier (meilleur pour l'algorithme et sans risque de droits d'auteur).

## Règles TikTok respectées
- Contenu original uniquement, aucun faux abonné ni fausse vue.
- Pense à activer **« Contenu généré par l'IA »** au moment de publier.
- Publication manuelle après ta validation. La publication automatique par l'API officielle de TikTok demande une application
  approuvée par TikTok : sans approbation, les vidéos ne peuvent être publiées qu'en privé.

## Tester sans réseau
```
OFFLINE=1 python main.py
```
Ce mode produit une vidéo complète, mais avec une voix muette et des fonds générés : il sert à vérifier le montage.
