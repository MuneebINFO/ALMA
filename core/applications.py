"""
Inventaire des applications installees sur la machine.

La configuration ne peut pas tout prevoir : on y declare les applications
courantes, avec leurs chemins exacts, mais l utilisateur en installe d autres.
Ce module va les chercher la ou Windows les range.

Deux sources, dans cet ordre :

  1. le MENU DEMARRER -- un simple parcours de dossiers, 96 raccourcis lus en
     0,03 seconde sur la machine de reference. C est la source normale ;
  2. la LISTE DU SYSTEME (Get-StartApps), qui ajoute les applications du
     Store, absentes du menu Demarrer sous forme de raccourci. Elle coute
     1,9 seconde, donc elle est mise en cache sur disque et n est consultee
     que si la premiere n a rien donne.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)

EXTENSIONS = (".lnk", ".url")
DUREE_CACHE = 24 * 3600          # une journee : on n installe pas si souvent

# Dossiers ou Windows range les raccourcis du menu Demarrer.
DOSSIERS_MENU = (
    (r"%ProgramData%", r"Microsoft\Windows\Start Menu\Programs"),
    (r"%APPDATA%", r"Microsoft\Windows\Start Menu\Programs"),
)

# Raccourcis qui ne sont pas des applications : outils d administration,
# desinstalleurs, documentation. Les proposer ne rendrait service a personne.
INDESIRABLES = (
    "uninstall", "desinstall", "readme", "documentation", "release notes",
    "faqs", "licence", "license", "manuel", "aide", "help", "website",
    "site web", "support", "changelog", "what s new",
)


def _dossiers_menu() -> list:
    dossiers = []
    for variable, suite in DOSSIERS_MENU:
        racine = os.path.expandvars(variable)
        if racine and not racine.startswith("%"):
            dossiers.append(os.path.join(racine, suite))
    return dossiers


def _indesirable(nom: str) -> bool:
    minuscule = nom.lower()
    return any(mot in minuscule for mot in INDESIRABLES)


def raccourcis_du_menu() -> dict:
    """Nom affiche -> chemin du raccourci, pour tout le menu Demarrer."""
    trouves = {}
    for dossier in _dossiers_menu():
        if not os.path.isdir(dossier):
            continue
        try:
            for racine, _sous, fichiers in os.walk(dossier):
                for fichier in fichiers:
                    if not fichier.lower().endswith(EXTENSIONS):
                        continue
                    nom = os.path.splitext(fichier)[0]
                    if _indesirable(nom):
                        continue
                    trouves.setdefault(nom, os.path.join(racine, fichier))
        except Exception as exc:
            log.debug("Menu Demarrer illisible (%s) : %s", dossier, exc)
    return trouves


def _chemin_cache() -> Path:
    # Le dossier de donnees de l utilisateur (config.DATA_DIR), pas un chemin
    # relatif au module : une fois Alma empaquetee (--onefile, MSIX...), ce
    # dernier pointerait dans un dossier temporaire ou en lecture seule.
    from config import DATA_DIR

    return DATA_DIR / "applications_installees.json"


def _lire_cache() -> dict | None:
    chemin = _chemin_cache()
    try:
        if not chemin.exists() or time.time() - chemin.stat().st_mtime > DUREE_CACHE:
            return None
        return json.loads(chemin.read_text(encoding="utf-8"))
    except Exception as exc:
        log.debug("Cache d applications illisible : %s", exc)
        return None


def _ecrire_cache(entrees: dict) -> None:
    chemin = _chemin_cache()
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(entrees, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    except Exception as exc:
        log.debug("Cache d applications non ecrit : %s", exc)


def applications_du_systeme(forcer: bool = False) -> dict:
    """
    Nom affiche -> identifiant de lancement, d apres la liste du systeme.

    Inclut les applications du Store, qui n ont pas de raccourci. Resultat
    garde en cache : l appel coute pres de deux secondes.
    """
    if not forcer:
        cache = _lire_cache()
        if cache is not None:
            return cache
    entrees = {}
    try:
        # Les noms d applications sont pleins d accents : on impose l UTF-8
        # des deux cotes, sinon la console repond en page de code locale et
        # le decodage echoue au premier caractere accentue.
        sortie = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        brut = (sortie.stdout or b"").decode("utf-8", errors="replace").strip()
        donnees = json.loads(brut or "[]")
        if isinstance(donnees, dict):
            donnees = [donnees]
        for entree in donnees:
            nom = str(entree.get("Name") or "").strip()
            identifiant = str(entree.get("AppID") or "").strip()
            if nom and identifiant and not _indesirable(nom):
                entrees.setdefault(nom, identifiant)
    except Exception as exc:
        log.debug("Liste des applications du systeme indisponible : %s", exc)
        return _lire_cache() or {}
    if entrees:
        _ecrire_cache(entrees)
    return entrees


# --------------------------------------------------------------------------
# Recherche
# --------------------------------------------------------------------------
def _mots(texte: str) -> list:
    from core import text_utils

    return [m for m in text_utils.tokenize(text_utils.normalize(texte)) if m]


def _rang(nom: str, voulu: str, mots_voulus: set):
    """
    Qualite de la correspondance, du meilleur au pire. None si aucune.

    Les deux derniers recours rattrapent la reconnaissance vocale, qui rend
    mal les noms de logiciels : « Claude » revient en « Cloud ». Les deux ne
    se ressemblent qu a 0,73 en lettres -- sous tout seuil raisonnable --
    mais leurs sonorites, klod et klu, coincident.
    """
    from core import deduction, text_utils

    norme = " ".join(_mots(nom))
    if not norme:
        return None
    if norme == voulu:
        return (0, len(norme))
    if voulu and voulu in norme:
        return (1, len(norme))
    if mots_voulus and mots_voulus <= set(_mots(nom)):
        return (2, len(norme))
    if text_utils.similarity(voulu, norme) >= 0.85:
        return (3, len(norme))
    if deduction.se_ressemblent(voulu, norme):
        return (4, len(norme))
    if deduction.memes_consonnes(voulu, norme):
        return (5, len(norme))
    return None


def chercher(nom_parle: str, forcer_systeme: bool = False):
    """
    Retrouve une application installee. Retourne (nom_affiche, cible) ou None.

    `cible` se donne telle quelle a `lancer()` : un chemin de raccourci, ou
    un identifiant d application du Store.
    """
    from core import text_utils

    voulu = " ".join(_mots(nom_parle or ""))
    if not voulu:
        return None
    mots_voulus = set(_mots(nom_parle))

    def meilleur(entrees):
        classees = []
        for nom, cible in entrees.items():
            rang = _rang(nom, voulu, mots_voulus)
            if rang is not None:
                classees.append((rang, nom, cible))
        if not classees:
            return None
        _rang_, nom, cible = min(classees, key=lambda item: item[0])
        return nom, cible

    # Le menu Demarrer d abord : instantane, et il couvre presque tout.
    trouve = meilleur(raccourcis_du_menu())
    if trouve is not None:
        return trouve
    return meilleur(applications_du_systeme(forcer=forcer_systeme))


def lancer(cible: str) -> tuple:
    """
    Demarre une application trouvee par `chercher`. Retourne (succes, detail).

    Un raccourci s ouvre directement ; une application du Store n a pas de
    fichier et se lance par son identifiant, via le dossier special que
    l explorateur sait resoudre.
    """
    if not cible:
        return False, "aucune cible"
    try:
        if os.path.exists(cible):
            os.startfile(cible)          # type: ignore[attr-defined]
            return True, cible
        subprocess.Popen(
            ["explorer.exe", "shell:AppsFolder" + os.sep + cible],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return True, cible
    except Exception as exc:
        return False, str(exc)
