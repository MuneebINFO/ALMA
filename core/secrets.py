"""
Le coffre : ce qu Alma detient et qui ne doit pas se lire.

Une seule chose y vit aujourd hui -- la cle d API de l edition complete, que
l utilisateur fournit lui-meme. Elle ne ressemble a aucun autre reglage :
les autres decrivent un gout (une voix, une ville, un nom), celle-ci ouvre un
compte facturable. La laisser en clair dans preferences.json la rendrait
lisible par n importe quel programme lance par le meme utilisateur, et la
ferait partir dans la premiere sauvegarde cloud venue.

Elle est donc chiffree par WINDOWS lui-meme (DPAPI), lie au compte de
l utilisateur : le fichier copie sur une autre machine, ou ouvert par un autre
compte, ne rend rien. Aucune dependance nouvelle -- pywin32 est deja la.

DEUX REGLES tenues par les tests.

Rien de ce module n ecrit jamais une valeur dans un journal, meme tronquee,
meme en debug : un extrait de cle dans un fichier de log est une cle fuitee.

Et `lire` ne leve pas. Un coffre illisible -- fichier abime, cle posee par un
autre compte Windows, pywin32 absent -- doit se comporter comme un coffre
vide : Alma retombe alors sur l edition libre, qui marche sans rien.
"""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Ce que Windows affichera si l utilisateur inspecte le blob chiffre.
DESCRIPTION = "ALMA"


def _fichier(config=None) -> Path:
    """Le coffre. A cote des preferences, mais jamais dans le meme fichier."""
    if config is not None:
        try:
            return Path(config.resolve_path("secrets", "data/secrets.json"))
        except Exception:                     # pragma: no cover - defensif
            pass
    from config import ROOT

    return ROOT / "data" / "secrets.json"


def _charger(config=None) -> dict:
    fichier = _fichier(config)
    try:
        with open(fichier, encoding="utf-8") as f:
            contenu = json.load(f)
        return contenu if isinstance(contenu, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}
    except OSError as exc:
        # Volontairement sans le contenu : un message d erreur qui cite le
        # fichier est utile, un qui cite ce qu il porte ne l est jamais.
        log.debug("Coffre illisible : %s", exc)
        return {}


def poser(nom: str, valeur: str, config=None) -> bool:
    """Chiffre `valeur` et la range sous `nom`. Rend True si c est ecrit."""
    if not nom:
        return False
    if not valeur:
        return oublier(nom, config)
    try:
        import win32crypt

        blob = win32crypt.CryptProtectData(
            valeur.encode("utf-8"), DESCRIPTION, None, None, None, 0)
    except Exception as exc:
        log.warning("Chiffrement impossible : %s", exc)
        return False

    coffre = _charger(config)
    coffre[nom] = base64.b64encode(blob).decode("ascii")
    fichier = _fichier(config)
    try:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(coffre, f, indent=2)
    except OSError as exc:
        log.warning("Coffre non ecrit : %s", exc)
        return False
    return True


def lire(nom: str, config=None) -> str:
    """
    La valeur en clair, ou une chaine vide.

    Ne leve jamais : un coffre illisible doit se comporter comme un coffre
    vide, sans quoi une cle posee depuis un autre compte Windows empecherait
    Alma de demarrer au lieu de la faire retomber en edition libre.
    """
    encode = _charger(config).get(nom)
    if not encode:
        return ""
    try:
        import win32crypt

        _description, clair = win32crypt.CryptUnprotectData(
            base64.b64decode(encode), None, None, None, 0)
        return clair.decode("utf-8")
    except Exception as exc:
        log.debug("Déchiffrement impossible pour « %s » : %s", nom, exc)
        return ""


def oublier(nom: str, config=None) -> bool:
    """Retire une valeur du coffre. True meme si elle n y etait pas."""
    coffre = _charger(config)
    if nom not in coffre:
        return True
    coffre.pop(nom, None)
    fichier = _fichier(config)
    try:
        if coffre:
            with open(fichier, "w", encoding="utf-8") as f:
                json.dump(coffre, f, indent=2)
        else:
            # Coffre vide : on retire le fichier plutot que de laisser un
            # « {} » qui laisse croire qu il reste quelque chose.
            fichier.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("Coffre non mis a jour : %s", exc)
        return False
    return True


def present(nom: str, config=None) -> bool:
    """Y a-t-il une valeur LISIBLE sous ce nom ?"""
    return bool(lire(nom, config))
