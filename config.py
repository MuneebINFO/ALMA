"""
Chargement de la configuration.

Le projet doit tourner SANS aucun fichier de config : les valeurs par defaut
ci-dessous suffisent. Si `config.yaml` existe, il est fusionne par-dessus
(fusion recursive), ce qui permet de n en redefinir qu une partie.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SCREENSHOT_DIR = ROOT / "screenshots"
DEFAULT_CONFIG_FILE = ROOT / "config.yaml"

DEFAULTS: dict = {
    "general": {
        "assistant_name": "ALMA",
        "user_name": "",
        "language": "fr",
        # --- mot d appel -----------------------------------------------------
        # Le nom prononce pour reveiller l assistant. Changer cette seule
        # valeur suffit a le renommer : aucun code a modifier.
        "wake_word": "alma",
        # Prefixes toleres avant le nom (« OK Alma », « dis Alma »).
        "wake_prefixes": ["ok", "hey", "he", "eh", "dis"],
        # Transcriptions supplementaires a accepter. Si l assistant ne repond
        # pas, regardez le texte affiche sous l orbe et ajoutez-le ici.
        "wake_variants": [],
        # true = le nom seul ne suffit plus, il faut « OK Alma » / « dis Alma ».
        # Utile si le nom choisi ressemble a un mot ou prenom courant.
        "wake_require_prefix": False,
        # Accepter une transcription approchante quand la phrase se reduit au
        # seul nom. C est le cas ou la reconnaissance vocale se trompe le plus
        # -- sans contexte, « Alma » revient souvent en « Elma » ou « Alba » --
        # et c est aussi celui ou l on ne fait qu appeler. Passez a false si un
        # mot proche du nom est prononce seul autour de vous.
        "wake_tolerate_alone": True,
        "confirm_dangerous_actions": True,
    },
    "voice": {
        "enabled": False,            # mode texte par defaut pour main.py
        "speak_responses": True,
        # --- synthese vocale ---
        "engine": "auto",            # auto | edge (neuronal) | sapi5 (local)
        "neural_voice": "fr-FR-DeniseNeural",
        "neural_rate": "+0%",
        "rate": 175,                 # vitesse SAPI5 (repli hors ligne)
        "volume": 1.0,
        "voice_id": "",
        # --- reconnaissance ---
        "stt_engine": "google",
        "stt_language": "fr-FR",
        "vosk_model_path": "",
        # Seuil de detection de la voix. Beaucoup de micros integres ont un
        # gain faible : ce plancher volontairement bas evite que Alma reste
        # sourd. Voir « python diagnostic_micro.py ».
        "min_threshold": 0.004,
        "noise_factor": 3.5,
        # Duree pendant laquelle Alma reste receptif apres un « Alma » seul.
        "armed_seconds": 60,
        "energy_threshold": 300,
        "pause_threshold": 0.8,
        "timeout": 6,
        "phrase_time_limit": 12,
    },
    "paths": {
        "notes": "data/notes.json",
        "reminders": "data/reminders.json",
        "history": "data/history.json",
        "screenshots": "screenshots",
        "music": "",
    },
    "weather": {
        "default_city": "Bruxelles",
        "units": "metric",
    },
    # Fallback IA : DESACTIVE par defaut (enabled: false).
    # Tant que enabled vaut False, aucun appel reseau ni sous-processus n est
    # declenche : les demandes non reconnues recoivent un message poli.
    "ai_fallback": {
        "enabled": False,
        "provider": "claude_code",
        "claude_code": {
            # Binaire du CLI Claude Code (doit etre dans le PATH).
            "command": "claude",
            # Dossier dans lequel Claude Code a le droit d agir. Volontairement
            # vide : il doit etre choisi explicitement avant toute utilisation.
            "working_dir": "",
            # L appel est bloquant : une tache complexe peut etre longue.
            "timeout_seconds": 120,
        },
    },
    # Defilement de page. Reglage par defaut mesure a ~365 pixels par seconde,
    # soit une vitesse de lecture confortable. Deux crans par tic depassent
    # 1300 px/s et deviennent illisibles : augmentez plutot avec prudence.
    "interaction": {
        "scroll_crans": 1,
        "scroll_intervalle": 0.25,
        "scroll_duree_max": 300,
    },
    "notifications": {
        "sound": True,
        "popup": True,
    },
    "folders": {
        "telechargements": "%USERPROFILE%/Downloads",
        "downloads": "%USERPROFILE%/Downloads",
        "documents": "%USERPROFILE%/Documents",
        "images": "%USERPROFILE%/Pictures",
        "photos": "%USERPROFILE%/Pictures",
        "bureau": "%USERPROFILE%/Desktop",
        "desktop": "%USERPROFILE%/Desktop",
        "musique": "%USERPROFILE%/Music",
        "music": "%USERPROFILE%/Music",
        "videos": "%USERPROFILE%/Videos",
        "telechargement": "%USERPROFILE%/Downloads",
    },
}

# --- Applications lancables ------------------------------------------------
# `paths` est une liste de candidats essayes dans l ordre : chemin complet,
# executable dans le PATH, ou URI shell (ex: ms-settings:).
DEFAULTS["applications"] = {
    "chrome": {
        "aliases": ["chrome", "google chrome", "navigateur", "browser"],
        "paths": [
            "chrome.exe",
            "%ProgramFiles%/Google/Chrome/Application/chrome.exe",
            "%LOCALAPPDATA%/Google/Chrome/Application/chrome.exe",
        ],
        "process": "chrome.exe",
    },
    "firefox": {
        "aliases": ["firefox", "mozilla", "mozilla firefox"],
        "paths": ["firefox.exe", "%ProgramFiles%/Mozilla Firefox/firefox.exe"],
        "process": "firefox.exe",
    },
    "edge": {
        "aliases": ["edge", "microsoft edge"],
        "paths": ["msedge.exe"],
        "process": "msedge.exe",
    },
    "notepad": {
        "aliases": ["bloc note", "bloc notes", "notepad", "le bloc note"],
        "paths": ["notepad.exe"],
        "process": "notepad.exe",
    },
    "calculator": {
        "aliases": ["calculatrice", "calculette", "calculator", "calc"],
        "paths": ["calc.exe"],
        "process": "CalculatorApp.exe",
    },
    "explorer": {
        "aliases": ["explorateur", "explorateur de fichiers", "explorer", "mes fichiers"],
        "paths": ["explorer.exe"],
        "process": "",
    },
    "vscode": {
        "aliases": ["vs code", "vscode", "visual studio code"],
        "paths": ["code.cmd", "code", "%LOCALAPPDATA%/Programs/Microsoft VS Code/Code.exe"],
        "process": "Code.exe",
    },
    "word": {
        "aliases": ["word", "microsoft word"],
        "paths": ["winword.exe"],
        "process": "WINWORD.EXE",
    },
    "excel": {
        "aliases": ["excel", "microsoft excel"],
        "paths": ["excel.exe"],
        "process": "EXCEL.EXE",
    },
    "powerpoint": {
        "aliases": ["powerpoint", "power point"],
        "paths": ["powerpnt.exe"],
        "process": "POWERPNT.EXE",
    },
    "outlook": {
        "aliases": ["outlook", "messagerie"],
        "paths": ["outlook.exe"],
        "process": "OUTLOOK.EXE",
    },
    "spotify": {
        "aliases": ["spotify"],
        "paths": ["%APPDATA%/Spotify/Spotify.exe", "spotify.exe", "spotify:"],
        "process": "Spotify.exe",
    },
    "discord": {
        "aliases": ["discord"],
        "paths": ["%LOCALAPPDATA%/Discord/Update.exe", "discord.exe"],
        "process": "Discord.exe",
    },
    "steam": {
        "aliases": ["steam"],
        "paths": ["%ProgramFiles(x86)%/Steam/steam.exe", "steam.exe"],
        "process": "steam.exe",
    },
    "paint": {
        "aliases": ["paint", "mspaint"],
        "paths": ["mspaint.exe"],
        "process": "mspaint.exe",
    },
    "cmd": {
        "aliases": ["invite de commande", "terminal", "cmd", "console"],
        "paths": ["cmd.exe"],
        "process": "cmd.exe",
    },
    "powershell": {
        "aliases": ["powershell"],
        "paths": ["powershell.exe"],
        "process": "powershell.exe",
    },
    "taskmanager": {
        "aliases": ["gestionnaire de taches", "task manager", "taskmgr"],
        "paths": ["taskmgr.exe"],
        "process": "",
    },
    "settings": {
        "aliases": ["parametres", "reglages", "settings"],
        "paths": ["ms-settings:"],
        "process": "",
    },
}

# --- Sites web -------------------------------------------------------------
DEFAULTS["websites"] = {
    "youtube": {"aliases": ["youtube", "you tube"], "url": "https://www.youtube.com"},
    "gmail": {"aliases": ["gmail", "mes emails", "ma boite mail"], "url": "https://mail.google.com"},
    "github": {"aliases": ["github", "git hub"], "url": "https://github.com"},
    "netflix": {"aliases": ["netflix"], "url": "https://www.netflix.com"},
    "google": {"aliases": ["google"], "url": "https://www.google.com"},
    "claude": {"aliases": ["claude", "claude ai"], "url": "https://claude.ai"},
    "chatgpt": {"aliases": ["chatgpt", "chat gpt"], "url": "https://chat.openai.com"},
    "wikipedia": {"aliases": ["wikipedia"], "url": "https://fr.wikipedia.org"},
    "maps": {"aliases": ["google maps", "maps", "la carte"], "url": "https://maps.google.com"},
    "drive": {"aliases": ["google drive", "drive", "mon drive"], "url": "https://drive.google.com"},
    "linkedin": {"aliases": ["linkedin"], "url": "https://www.linkedin.com"},
    "twitch": {"aliases": ["twitch"], "url": "https://www.twitch.tv"},
    "reddit": {"aliases": ["reddit"], "url": "https://www.reddit.com"},
    "instagram": {"aliases": ["instagram", "insta"], "url": "https://www.instagram.com"},
    "whatsapp": {"aliases": ["whatsapp", "whats app"], "url": "https://web.whatsapp.com"},
    "deepl": {"aliases": ["deepl"], "url": "https://www.deepl.com/translator"},
    "stackoverflow": {"aliases": ["stack overflow", "stackoverflow"], "url": "https://stackoverflow.com"},
    "amazon": {"aliases": ["amazon"], "url": "https://www.amazon.fr"},
    "leboncoin": {"aliases": ["leboncoin", "le bon coin"], "url": "https://www.leboncoin.fr"},
    "twitter": {"aliases": ["twitter", "x"], "url": "https://x.com"},
}


class Config:
    """Acces a la configuration par chemins pointes : cfg.get("voice.enabled")."""

    def __init__(self, data: dict | None = None, source: Path | None = None) -> None:
        self.data = data if data is not None else copy.deepcopy(DEFAULTS)
        self.source = source

    def get(self, path: str, default=None):
        node = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, path: str, value) -> None:
        parts = path.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def __getitem__(self, key):
        return self.data[key]

    def resolve_path(self, path_key: str, default: str = "") -> Path:
        """Resout une entree de la section paths en chemin absolu."""
        raw = self.get("paths." + path_key, default) or default
        expanded = os.path.expandvars(os.path.expanduser(str(raw)))
        candidate = Path(expanded)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        return candidate


def deep_merge(base: dict, override: dict) -> dict:
    """Fusion recursive de deux dictionnaires (override gagne)."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_dotenv() -> None:
    """Lecture minimaliste d un fichier .env, sans dependance externe."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"").strip("\'"))
    except Exception:
        pass


def load_config(path: str | Path | None = None) -> Config:
    """
    Charge la configuration :
      1. valeurs par defaut (toujours presentes, aucun fichier requis)
      2. config.yaml s il existe (fusion recursive)
      3. variables d environnement (mode voix uniquement)
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_FILE
    data = copy.deepcopy(DEFAULTS)
    source = None

    if config_path.exists():
        try:
            import yaml

            with open(config_path, "r", encoding="utf-8") as handle:
                user_data = yaml.safe_load(handle) or {}
            data = deep_merge(data, user_data)
            source = config_path
        except ImportError:
            print("[config] PyYAML absent : config.yaml ignore, valeurs par defaut utilisees.")
        except Exception as exc:
            print("[config] Lecture de " + str(config_path) + " impossible : " + str(exc))

    _load_dotenv()
    # Aucune cle API n est lue ni ecrite ici : la seule porte d entree IA est le
    # CLI Claude Code, qui gere lui-meme son authentification. En particulier,
    # Alma ne touche JAMAIS a ANTHROPIC_API_KEY (voir core/providers/).
    if os.environ.get("ALMA_VOICE", "").lower() in ("1", "true", "yes", "on"):
        data["voice"]["enabled"] = True

    # Les mots d appel utilises pour nettoyer une phrase tapee sont derives
    # du nom configure : un seul endroit a changer pour renommer l assistant.
    mot = str(data["general"].get("wake_word", "alma") or "alma").strip().lower()
    prefixes = data["general"].get("wake_prefixes", []) or []
    data["general"]["wake_words"] = [mot] + [
        str(prefixe).strip().lower() + " " + mot for prefixe in prefixes
    ]

    DATA_DIR.mkdir(exist_ok=True)
    return Config(data, source)


# --- Recherche a l interieur des sites --------------------------------------
# `search_url` permet a « va sur Netflix et mets Fast and Furious » d aller
# directement au bon resultat. {q} est remplace par la requete, encodee.
_RECHERCHES = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "netflix": "https://www.netflix.com/search?q={q}",
    "google": "https://www.google.com/search?q={q}",
    "github": "https://github.com/search?q={q}",
    "wikipedia": "https://fr.wikipedia.org/w/index.php?search={q}",
    "amazon": "https://www.amazon.fr/s?k={q}",
    "twitch": "https://www.twitch.tv/search?term={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "leboncoin": "https://www.leboncoin.fr/recherche?text={q}",
    "maps": "https://www.google.com/maps/search/{q}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q={q}",
    "twitter": "https://x.com/search?q={q}",
    "drive": "https://drive.google.com/drive/search?q={q}",
    "gmail": "https://mail.google.com/mail/u/0/#search/{q}",
}
for _cle, _url in _RECHERCHES.items():
    if _cle in DEFAULTS["websites"]:
        DEFAULTS["websites"][_cle]["search_url"] = _url

# --- Plateformes supplementaires --------------------------------------------
DEFAULTS["websites"].update({
    "primevideo": {
        "aliases": ["prime video", "amazon prime", "prime"],
        "url": "https://www.primevideo.com",
        "search_url": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase={q}",
    },
    "disney": {
        "aliases": ["disney plus", "disney+", "disney"],
        "url": "https://www.disneyplus.com",
        "search_url": "https://www.disneyplus.com/search?q={q}",
    },
    "crunchyroll": {
        "aliases": ["crunchyroll", "crunchy"],
        "url": "https://www.crunchyroll.com",
        "search_url": "https://www.crunchyroll.com/search?q={q}",
    },
    "spotifyweb": {
        "aliases": ["spotify web", "spotify en ligne"],
        "url": "https://open.spotify.com",
        "search_url": "https://open.spotify.com/search/{q}",
    },
    "deezer": {
        "aliases": ["deezer"],
        "url": "https://www.deezer.com",
        "search_url": "https://www.deezer.com/search/{q}",
    },
    "soundcloud": {
        "aliases": ["soundcloud", "sound cloud"],
        "url": "https://soundcloud.com",
        "search_url": "https://soundcloud.com/search?q={q}",
    },
    "dailymotion": {
        "aliases": ["dailymotion", "daily motion"],
        "url": "https://www.dailymotion.com",
        "search_url": "https://www.dailymotion.com/search/{q}",
    },
    "tiktok": {
        "aliases": ["tiktok", "tik tok"],
        "url": "https://www.tiktok.com",
        "search_url": "https://www.tiktok.com/search?q={q}",
    },
    "imdb": {
        "aliases": ["imdb"],
        "url": "https://www.imdb.com",
        "search_url": "https://www.imdb.com/find/?q={q}",
    },
    "allocine": {
        "aliases": ["allocine", "allo cine"],
        "url": "https://www.allocine.fr",
        "search_url": "https://www.allocine.fr/rechercher/?q={q}",
    },
    "auvio": {
        "aliases": ["auvio", "rtbf", "la rtbf"],
        "url": "https://auvio.rtbf.be",
        "search_url": "https://auvio.rtbf.be/recherche?q={q}",
    },
    "francetv": {
        "aliases": ["france tv", "francetv"],
        "url": "https://www.france.tv",
        "search_url": "https://www.france.tv/recherche/?q={q}",
    },
    "ebay": {
        "aliases": ["ebay"],
        "url": "https://www.ebay.fr",
        "search_url": "https://www.ebay.fr/sch/i.html?_nkw={q}",
    },
    "pinterest": {
        "aliases": ["pinterest"],
        "url": "https://www.pinterest.com",
        "search_url": "https://www.pinterest.com/search/pins/?q={q}",
    },
    "booking": {
        "aliases": ["booking", "booking com"],
        "url": "https://www.booking.com",
        "search_url": "https://www.booking.com/searchresults.fr.html?ss={q}",
    },
})
