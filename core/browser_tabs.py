"""
Acces aux onglets des navigateurs, via UI Automation.

Pourquoi ce module : Windows n expose dans le titre d une fenetre que son
onglet ACTIF. Chercher « youtube » dans les titres ne trouve donc rien si
YouTube est ouvert en arriere-plan -- et l assistant ouvrait un onglet de plus
alors que le bon existait deja.

UI Automation (l API d accessibilite de Windows) voit en revanche TOUS les
onglets, et permet d en activer un. C est ce que fait un lecteur d ecran.

Limite connue : Firefox n expose par defaut que son onglet actif. Chrome, Edge
et les navigateurs derives de Chromium exposent la totalite.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

TYPE_ONGLET = 50019          # UIA_TabItemControlTypeId
_uia = None
_module = None


def _client():
    """Client UI Automation, cree une seule fois."""
    global _uia, _module
    if _uia is not None:
        return _uia, _module
    try:
        import comtypes
        import comtypes.client

        try:
            comtypes.CoInitialize()
        except Exception:
            pass       # deja initialise dans ce thread
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as module

        _uia = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=module.IUIAutomation
        )
        _module = module
    except Exception as exc:
        log.debug("UI Automation indisponible : %s", exc)
        return None, None
    return _uia, _module


@dataclass
class Onglet:
    """Un onglet de navigateur."""

    nom: str
    fenetre: object          # la Fenetre qui le contient
    element: object          # l element UI Automation, pour l activer

    def activer(self) -> bool:
        """Met cet onglet au premier plan dans sa fenetre."""
        _client_uia, module = _client()
        if module is None:
            return False
        try:
            motif = self.element.GetCurrentPattern(module.UIA_SelectionItemPatternId)
            selection = motif.QueryInterface(module.IUIAutomationSelectionItemPattern)
            selection.Select()
            return True
        except Exception as exc:
            log.debug("Activation de l onglet impossible : %s", exc)
            return False


# La barre d adresse, telle que les navigateurs l annoncent.
NOMS_BARRE_ADRESSE = ("adresse", "address", "url", "recherche", "search")
TYPE_CHAMP = 50004           # UIA_EditControlTypeId


def adresse_courante(fenetre) -> str:
    """
    L adresse affichee dans la barre du navigateur, ou "" si illisible.

    Chrome n y montre pas le protocole (« youtube.com/watch?v=... ») : c est
    au lecteur d en tenir compte.
    """
    uia, module = _client()
    if uia is None:
        return ""
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        condition = uia.CreatePropertyCondition(module.UIA_ControlTypePropertyId,
                                                TYPE_CHAMP)
        champs = racine.FindAll(module.TreeScope_Descendants, condition)
    except Exception as exc:
        log.debug("Barre d adresse illisible : %s", exc)
        return ""
    for index in range(champs.Length):
        try:
            champ = champs.GetElement(index)
            nom = (champ.CurrentName or "").lower()
            if not any(mot in nom for mot in NOMS_BARRE_ADRESSE):
                continue
            motif = champ.GetCurrentPattern(module.UIA_ValuePatternId)
            if not motif:
                continue
            valeur = motif.QueryInterface(module.IUIAutomationValuePattern).CurrentValue
            if valeur:
                return str(valeur).strip()
        except Exception:
            continue
    return ""


def racine_du_site(adresse: str) -> str:
    """
    L accueil du site auquel appartient une adresse.

    « youtube.com/watch?v=abc » donne « https://youtube.com/ ». Retourne ""
    si ce n est pas une adresse -- la barre peut contenir une recherche.
    """
    adresse = (adresse or "").strip()
    if not adresse or " " in adresse:
        return ""
    protocole = "https://"
    if "://" in adresse:
        protocole, _, adresse = adresse.partition("://")
        protocole += "://"
        if protocole not in ("http://", "https://"):
            return ""
    hote = adresse.split("/")[0].split("?")[0].split("#")[0]
    if "." not in hote or hote.startswith(".") or hote.endswith("."):
        return ""
    return protocole + hote + "/"


def onglets(fenetre) -> list:
    """Liste les onglets d une fenetre de navigateur."""
    uia, module = _client()
    if uia is None:
        return []
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        condition = uia.CreatePropertyCondition(module.UIA_ControlTypePropertyId, TYPE_ONGLET)
        trouves = racine.FindAll(module.TreeScope_Descendants, condition)
    except Exception as exc:
        log.debug("Lecture des onglets impossible : %s", exc)
        return []

    resultat = []
    for index in range(trouves.Length):
        try:
            element = trouves.GetElement(index)
            resultat.append(Onglet(element.CurrentName or "", fenetre, element))
        except Exception:
            continue
    return resultat


def _nettoyer(nom: str) -> str:
    """
    Retire les mentions ajoutees par le navigateur au nom d un onglet
    (« - Utilisation de la mémoire - 293 Mo », « Lecture audio »...).
    """
    from core import text_utils

    nom = text_utils.normalize(nom)
    for parasite in ("utilisation de la memoire", "memory usage", "lecture audio",
                     "audio playing", "muet", "muted"):
        nom = nom.replace(parasite, " ")
    return " ".join(nom.split())


def trouver_onglet(termes, fenetres=None, ecran: int | None = None):
    """
    Cherche, dans les fenetres de navigateur, un onglet dont le nom contient
    l un des termes. Retourne l Onglet ou None.

    `ecran`, quand il est precise, est une FRONTIERE, pas une preference :
    seuls les onglets de cet ecran comptent. Reprendre un onglet d un autre
    ecran serait invisible pour l utilisateur, qui ne regarde pas cet
    ecran-la.
    """
    from core import desktop, text_utils

    if isinstance(termes, str):
        termes = [termes]
    termes = [text_utils.normalize(t).strip() for t in termes if t]
    if not termes:
        return None

    if fenetres is None:
        fenetres = [f for f in desktop.fenetres() if f.est_navigateur]
    if ecran is not None:
        fenetres = [f for f in fenetres if f.ecran == ecran]

    for fenetre in fenetres:
        for onglet in onglets(fenetre):
            nom = _nettoyer(onglet.nom)
            if any(terme in nom for terme in termes):
                return onglet
    return None
