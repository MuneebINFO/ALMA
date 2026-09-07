"""
Volume propre au lecteur de la page (YouTube, Netflix, Twitch, Prime Video...).

Une video de site de streaming a son propre niveau, independant du volume de
l ordinateur. Ce module le pilote comme le ferait un lecteur d ecran :

  1. LIRE -- le curseur de volume du lecteur est expose par l API
     d accessibilite avec sa valeur et ses bornes, meme quand la barre de
     controle est masquee ;
  2. AGIR -- l ECRITURE de cette valeur est ignoree par les lecteurs web (leur
     curseur est un <div role="slider">, pas un vrai controle : rien n ecoute
     l appel). On donne donc le focus au curseur et on envoie des fleches,
     exactement comme un utilisateur au clavier.

Le pas d une fleche varie d un site a l autre. Plutot que de le supposer, on
le MESURE apres la premiere salve et on ajuste : le meme code atteint donc une
valeur precise sur un lecteur a 5 % par cran comme sur un lecteur a 10 %.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Le nom du curseur, tel que les lecteurs l annoncent. « volume » couvre le
# francais, l anglais, l espagnol et l italien ; les autres sont explicites.
MOTS_VOLUME = ("volume", "volumen", "lautstarke", "sound", "audio")

TYPE_CURSEUR = 50015        # UIA_SliderControlTypeId
VK_HAUT, VK_BAS = 0x26, 0x28

PAS_SUPPOSE = 5.0           # pas d une fleche, avant mesure
TOLERANCE = 3               # a 3 points pres, on considere la cible atteinte
SALVES_MAX = 5              # nombre d aller-retours mesure/correction
TOUCHES_MAX = 25            # garde-fou : jamais plus par salve
PAUSE_TOUCHE = 0.03
PAUSE_LECTURE = 0.25


@dataclass
class CurseurVolume:
    """Le curseur de volume d un lecteur, lu par l API d accessibilite."""

    element: object
    motif: object
    minimum: float
    maximum: float

    @property
    def valeur(self) -> float:
        """Niveau ramene sur 0-100, quelles que soient les bornes du lecteur."""
        try:
            brut = float(self.motif.CurrentValue)
        except Exception:
            return -1.0
        etendue = self.maximum - self.minimum
        if etendue <= 0:
            return -1.0
        return max(0.0, min(100.0, (brut - self.minimum) / etendue * 100.0))


def _est_un_volume(nom: str) -> bool:
    from core import text_utils

    nom = text_utils.normalize(nom or "").lower()
    return any(mot in nom for mot in MOTS_VOLUME)


def trouver(fenetre) -> CurseurVolume | None:
    """Le curseur de volume du lecteur affiche dans cette fenetre."""
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if uia is None:
        return None
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        tous = racine.FindAll(module.TreeScope_Descendants, uia.CreateTrueCondition())
    except Exception as exc:
        log.debug("Lecture de la fenetre impossible : %s", exc)
        return None

    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            if not _est_un_volume(element.CurrentName):
                continue
            motif = element.GetCurrentPattern(module.UIA_RangeValuePatternId)
            if not motif:
                continue
            concret = motif.QueryInterface(module.IUIAutomationRangeValuePattern)
            minimum = float(concret.CurrentMinimum)
            maximum = float(concret.CurrentMaximum)
            if maximum <= minimum:
                continue
            return CurseurVolume(element, concret, minimum, maximum)
        except Exception:
            continue
    return None


def lire(fenetre) -> int | None:
    """Niveau actuel du lecteur, en pourcentage."""
    curseur = trouver(fenetre)
    if curseur is None:
        return None
    valeur = curseur.valeur
    return None if valeur < 0 else int(round(valeur))


def _preparer(fenetre, curseur: CurseurVolume) -> bool:
    """
    Met la fenetre au premier plan et donne le focus au curseur.

    Les fleches vont a la fenetre active : sans cette etape, elles
    partiraient dans une autre application.
    """
    from core import desktop

    try:
        import ctypes

        actif = ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        actif = 0
    if actif != fenetre.handle and not desktop.mettre_au_premier_plan(fenetre.handle):
        return False
    try:
        curseur.element.SetFocus()
    except Exception as exc:
        log.debug("Focus du curseur impossible : %s", exc)
        return False
    time.sleep(PAUSE_LECTURE)
    return True


def regler(fenetre, cible: int) -> int | None:
    """
    Amene le volume du lecteur a `cible` (0-100). Retourne le niveau atteint,
    ou None si la fenetre n expose aucun curseur de volume.
    """
    cible = max(0, min(100, int(cible)))
    curseur = trouver(fenetre)
    if curseur is None or curseur.valeur < 0:
        return None
    if not _preparer(fenetre, curseur):
        return None

    from core import win_utils

    pas = PAS_SUPPOSE
    for _ in range(SALVES_MAX):
        avant = curseur.valeur
        ecart = cible - avant
        if abs(ecart) <= TOLERANCE:
            break
        touches = max(1, min(TOUCHES_MAX, int(round(abs(ecart) / max(pas, 1.0)))))
        code = VK_HAUT if ecart > 0 else VK_BAS
        for _ in range(touches):
            win_utils.press_key(code)
            time.sleep(PAUSE_TOUCHE)
        time.sleep(PAUSE_LECTURE)
        parcouru = abs(curseur.valeur - avant)
        if parcouru < 0.5:
            # Butee atteinte, ou lecteur sourd aux fleches : insister ne
            # servirait qu a marteler le clavier.
            break
        pas = parcouru / touches      # le pas reel du lecteur, mesure
    valeur = curseur.valeur
    return None if valeur < 0 else int(round(valeur))


def ajuster(fenetre, delta: int) -> int | None:
    """Monte ou baisse le volume du lecteur de `delta` points."""
    actuel = lire(fenetre)
    if actuel is None:
        return None
    return regler(fenetre, actuel + int(delta))
