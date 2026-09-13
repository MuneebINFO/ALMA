"""
Ce que l utilisateur a personnalise, et qui doit lui survivre.

Alma se renomme, apprend votre prenom, change de voix ou de langue -- a la
voix, en une phrase -- et doit s en souvenir au prochain lancement. C est
tout l objet de ce module.

POURQUOI UN FICHIER A PART, et pas config.yaml : ecrire du YAML par-dessus
un fichier ecrit a la main en detruirait les commentaires, qui sont
justement ce qui le rend lisible. La separation dit aussi quelque chose de
vrai : config.yaml est ce que VOUS avez regle, preferences.json est ce
qu Alma a retenu de vous. Le second gagne, parce qu il est plus recent et
qu il vient d un ordre explicite.

Seuls les reglages listes dans CATALOGUE peuvent etre ecrits : une commande
ne doit jamais pouvoir toucher un chemin de configuration quelconque.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reglage:
    """Un reglage personnalisable, et de quoi le presenter a l utilisateur."""

    chemin: str          # chemin dans la configuration (« general.user_name »)
    libelle_fr: str
    libelle_en: str
    # Certains reglages ne se decident pas seuls : le mot d appel DECOULE du
    # nom, la langue d ecoute de la langue choisie, le debit de la voix locale
    # de celui de la voix neuronale. Ils sont bien retenus -- il le faut,
    # sinon ils ne survivraient pas au redemarrage -- mais les lister
    # reviendrait a montrer deux fois la meme decision.
    visible: bool = True
    unite_fr: str = ""
    unite_en: str = ""

    def libelle(self, langue: str) -> str:
        return self.libelle_en if langue == "en" else self.libelle_fr

    def unite(self, langue: str) -> str:
        return self.unite_en if langue == "en" else self.unite_fr


# L inventaire complet de ce qui se personnalise. Il sert a trois choses :
# autoriser l ecriture, lister les preferences, et les oublier.
CATALOGUE = (
    # -- identite ------------------------------------------------------------
    Reglage("general.assistant_name", "mon nom", "my name"),
    Reglage("general.wake_word", "le mot qui me réveille", "the word that wakes me",
            visible=False),
    Reglage("general.user_name", "votre nom", "your name"),
    Reglage("general.setup_done", "la configuration initiale",
            "the initial setup", visible=False),
    # -- langue et voix ------------------------------------------------------
    Reglage("general.language", "la langue", "the language"),
    Reglage("voice.stt_language", "la langue que j'écoute", "the language I listen for",
            visible=False),
    Reglage("voice.speak_responses", "la lecture à voix haute", "reading out loud"),
    Reglage("voice.neural_voice", "ma voix", "my voice"),
    Reglage("voice.neural_rate", "mon débit", "my speaking rate"),
    Reglage("voice.rate", "mon débit (voix locale)", "my speaking rate (local voice)",
            visible=False),
    # -- comportement --------------------------------------------------------
    Reglage("general.confirm_dangerous_actions",
            "la confirmation avant une action risquée",
            "asking before a risky action"),
    Reglage("voice.armed_seconds", "le temps où je reste éveillé",
            "how long I stay awake", unite_fr=" secondes", unite_en=" seconds"),
    Reglage("voice.min_threshold", "ma sensibilité au micro", "my microphone sensitivity"),
    # -- contenu -------------------------------------------------------------
    Reglage("weather.default_city", "votre ville", "your city"),
    Reglage("paths.music", "votre dossier de musique", "your music folder"),
)

PAR_CHEMIN = {reglage.chemin: reglage for reglage in CATALOGUE}


# --------------------------------------------------------------------------
# Voix et langues
# --------------------------------------------------------------------------
# Une voix par langue et par genre. Changer de langue garde le genre choisi,
# et changer de genre garde la langue : les deux reglages sont portes par le
# meme champ, il faut donc savoir passer de l un a l autre.
VOIX = {
    ("fr", "femme"): "fr-FR-DeniseNeural",
    ("fr", "homme"): "fr-FR-HenriNeural",
    ("en", "femme"): "en-US-AriaNeural",
    ("en", "homme"): "en-US-GuyNeural",
}

LANGUE_ECOUTEE = {"fr": "fr-FR", "en": "en-US"}


def genre_de_la_voix(voix: str) -> str:
    """« homme » ou « femme » pour une voix donnee ; femme par defaut."""
    for (_langue, genre), nom in VOIX.items():
        if nom == voix:
            return genre
    return "femme"


def langue_de_la_voix(voix: str) -> str:
    """« fr » ou « en » pour une voix donnee ; le francais par defaut."""
    for (langue, _genre), nom in VOIX.items():
        if nom == voix:
            return langue
    return str(voix or "fr")[:2] if str(voix or "").startswith("en") else "fr"


def voix_pour(langue: str, genre: str) -> str:
    """La voix neuronale correspondant a une langue et un genre."""
    return VOIX.get((langue, genre)) or VOIX[("fr", "femme")]


# --------------------------------------------------------------------------
# Le magasin
# --------------------------------------------------------------------------
class Preferences:
    """
    Les personnalisations, sur le disque, en JSON : {chemin: valeur}.

    Volontairement minuscule et tolerant : un fichier illisible ne doit
    jamais empecher Alma de demarrer -- on repart alors de rien plutot que
    de refuser de se lancer.
    """

    def __init__(self, chemin: Path | str) -> None:
        self.chemin = Path(chemin)

    def charger(self) -> dict:
        """Ce qui a ete retenu, ou un dictionnaire vide."""
        try:
            if not self.chemin.exists():
                return {}
            donnees = json.loads(self.chemin.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Préférences illisibles (%s) : %s", self.chemin, exc)
            return {}
        if not isinstance(donnees, dict):
            return {}
        # On ne rend que ce qui est au catalogue : un fichier bricole a la
        # main ne doit pas pouvoir reecrire n importe quel reglage.
        return {cle: valeur for cle, valeur in donnees.items() if cle in PAR_CHEMIN}

    def _ecrire(self, donnees: dict) -> bool:
        try:
            self.chemin.parent.mkdir(parents=True, exist_ok=True)
            self.chemin.write_text(
                json.dumps(donnees, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return True
        except Exception as exc:
            log.warning("Préférences non enregistrées (%s) : %s", self.chemin, exc)
            return False

    def definir(self, chemin: str, valeur) -> bool:
        """Retient un reglage. False si le chemin n est pas personnalisable."""
        if chemin not in PAR_CHEMIN:
            return False
        donnees = self.charger()
        donnees[chemin] = valeur
        return self._ecrire(donnees)

    def definir_plusieurs(self, valeurs: dict) -> bool:
        """
        Plusieurs reglages d un coup, en une seule ecriture.

        Necessaire des qu un ordre en touche plusieurs : se renommer change
        le nom ET le mot d appel, et il ne doit pas exister d instant ou
        l un est ecrit et l autre non.
        """
        retenus = {c: v for c, v in valeurs.items() if c in PAR_CHEMIN}
        if not retenus:
            return False
        donnees = self.charger()
        donnees.update(retenus)
        return self._ecrire(donnees)

    def oublier(self, chemin: str) -> bool:
        """Retire un reglage : la valeur par defaut reprend la main."""
        donnees = self.charger()
        if chemin not in donnees:
            return False
        del donnees[chemin]
        return self._ecrire(donnees)

    def tout_oublier(self) -> int:
        """Efface toutes les personnalisations. Retourne combien il y en avait."""
        donnees = self.charger()
        if not donnees:
            return 0
        self._ecrire({})
        return len(donnees)
