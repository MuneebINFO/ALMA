"""
Volume propre au lecteur de la page (YouTube, Netflix, Prime Video...).

Une video de site de streaming a son propre niveau, independant du volume de
l ordinateur. Ce module le pilote comme le ferait un lecteur d ecran : il LIT
le curseur du lecteur par l API d accessibilite, et AGIT au clavier.

Pourquoi pas simplement ecrire la valeur ? Parce que l ecriture est ignoree :
le curseur d un lecteur web est un <div role="slider">, et rien dans la page
n ecoute l appel d accessibilite. Mesure faite sur YouTube : trois ecritures
consecutives, aucun changement. Les fleches, elles, passent par le meme
chemin qu un vrai utilisateur.

Les trois lecteurs mesures ne se ressemblent pas :

    lecteur       curseur     visible au repos   revele par        pas
    YouTube       « Volume »  oui                --                5
    Prime Video   « Volume »  non (3 s)          survol du lecteur 1
    Netflix       sans nom    non                survol du BOUTON  5 %

D ou trois principes : on reveille la barre de controle avant de chercher,
on accepte un curseur sans nom s il est colle au bouton de volume, et on
MESURE le pas au lieu de le supposer.
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Le nom du curseur, tel que les lecteurs l annoncent. « volume » couvre le
# francais, l anglais, l espagnol et l italien ; les autres sont explicites.
MOTS_VOLUME = ("volume", "volumen", "lautstarke", "sound", "audio")

TYPE_CURSEUR = 50015        # UIA_SliderControlTypeId
TYPE_BOUTON = 50000         # UIA_ButtonControlTypeId

VK_HAUT, VK_BAS = 0x26, 0x28
VK_PAGE_HAUT, VK_PAGE_BAS = 0x21, 0x22

PAS_SUPPOSE = 5.0           # pas d une fleche, avant mesure
TOLERANCE = 1               # a 1 point pres, la cible est atteinte
SALVES_MAX = 6              # aller-retours mesure/correction
TOUCHES_MAX = 40            # garde-fou : jamais plus par salve
PAUSE_TOUCHE = 0.03
PAUSE_LECTURE = 0.25
PAUSE_REVEIL = 0.35

# Un curseur sans nom n est retenu que s il jouxte le bouton de volume.
DISTANCE_BOUTON = 260

# Un pas d un point demande cent appuis pour traverser l echelle. Sous ce
# seuil, on tente une touche a gros pas -- et on ne la garde que si elle
# deplace vraiment le curseur.
PAS_TROP_FIN = 2.0
ECART_GROS_PAS = 15
GAIN_GROS_PAS = 5.0


@dataclass
class CurseurVolume:
    """Le curseur de volume d un lecteur, lu par l API d accessibilite."""

    element: object
    motif: object
    minimum: float
    maximum: float

    @property
    def valeur(self) -> float:
        """
        Niveau ramene sur 0-100.

        Les bornes varient : 0-100 sur YouTube et Prime Video, 0-1 sur
        Netflix. Tout le reste du module raisonne en pourcentage.
        """
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


# --------------------------------------------------------------------------
# Lecture de l arbre d accessibilite
# --------------------------------------------------------------------------
def _elements(fenetre):
    """Tous les elements de la fenetre, ou None si l arbre est illisible."""
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if uia is None:
        return None, None
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        return racine.FindAll(module.TreeScope_Descendants,
                              uia.CreateTrueCondition()), module
    except Exception as exc:
        log.debug("Lecture de la fenetre impossible : %s", exc)
        return None, None


def _plage(element, module):
    """Le motif « valeur dans un intervalle » d un element, ou None."""
    try:
        motif = element.GetCurrentPattern(module.UIA_RangeValuePatternId)
        if not motif:
            return None
        concret = motif.QueryInterface(module.IUIAutomationRangeValuePattern)
        minimum, maximum = float(concret.CurrentMinimum), float(concret.CurrentMaximum)
        if maximum <= minimum:
            return None
        return CurseurVolume(element, concret, minimum, maximum)
    except Exception:
        return None


def _chercher(fenetre) -> CurseurVolume | None:
    """Un curseur NOMME « volume », tel qu il est expose a cet instant."""
    tous, module = _elements(fenetre)
    if tous is None:
        return None
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            # Le nom doit etre celui du curseur, pas celui d un conteneur qui
            # recopie ceux de ses enfants : « Play Volume Plein ecran »...
            nom = (element.CurrentName or "").strip()
            if len(nom) > 24 or not _est_un_volume(nom):
                continue
            curseur = _plage(element, module)
            if curseur is not None:
                return curseur
        except Exception:
            continue
    return None


def _bouton_volume(fenetre):
    """Rectangle du bouton de volume, celui qu il faut survoler (Netflix)."""
    tous, _module = _elements(fenetre)
    if tous is None:
        return None
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            nom = (element.CurrentName or "").strip()
            if element.CurrentControlType != TYPE_BOUTON:
                continue
            if len(nom) > 24 or not _est_un_volume(nom):
                continue
            r = element.CurrentBoundingRectangle
            if r.right > r.left and r.bottom > r.top:
                return (r.left, r.top, r.right, r.bottom)
        except Exception:
            continue
    return None


def _curseur_pres_de(fenetre, rect) -> CurseurVolume | None:
    """
    Un curseur SANS NOM colle au bouton de volume.

    Netflix n annonce pas son curseur : seul son voisinage avec le bouton
    permet de le distinguer de la barre de progression, qui est nommee.
    """
    tous, module = _elements(fenetre)
    if tous is None:
        return None
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            if element.CurrentControlType != TYPE_CURSEUR:
                continue
            nom = (element.CurrentName or "").strip()
            if nom and not _est_un_volume(nom):
                continue          # barre de progression, reglage de vitesse...
            r = element.CurrentBoundingRectangle
            if (abs(r.left - rect[0]) > DISTANCE_BOUTON
                    or abs(r.top - rect[1]) > DISTANCE_BOUTON):
                continue
            curseur = _plage(element, module)
            if curseur is not None:
                return curseur
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------
# Reveiller la barre de controle
# --------------------------------------------------------------------------
def _centre_de_la_fenetre(fenetre):
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(fenetre.handle, ctypes.byref(rect)):
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
    except Exception as exc:
        log.debug("Rectangle de la fenetre inconnu : %s", exc)
        return None


class _Souris:
    """Deplace le pointeur et retient d ou il vient, pour l y remettre."""

    def __init__(self):
        from core import interaction

        self._interaction = interaction
        try:
            self.depart = interaction.position_souris()
        except Exception:
            self.depart = None

    def poser(self, point) -> bool:
        """Amene le pointeur sur un point, avec un vrai mouvement."""
        if point is None:
            return False
        try:
            # Deux deplacements : un saut unique peut ne declencher aucun
            # evenement de survol et ne rien reveiller.
            self._interaction.deplacer_souris(point[0], point[1])
            time.sleep(0.12)
            self._interaction.deplacer_souris(point[0] + 3, point[1] + 1)
            time.sleep(PAUSE_REVEIL)
            return True
        except Exception as exc:
            log.debug("Deplacement du pointeur impossible : %s", exc)
            return False

    def revenir(self) -> None:
        if self.depart is None:
            return
        try:
            self._interaction.deplacer_souris(*self.depart)
        except Exception:
            pass


@contextlib.contextmanager
def reveler(fenetre):
    """
    Rend le curseur de volume accessible et l y maintient le temps d agir.

    Les lecteurs referment leur barre de controle apres quelques secondes et
    en retirent le curseur : le pointeur doit donc rester dessus pendant
    toute l operation, puis retrouver sa place.
    """
    souris = _Souris()
    try:
        curseur = _chercher(fenetre)
        if curseur is not None:
            yield curseur            # YouTube : toujours la, rien a faire
            return
        souris.poser(_centre_de_la_fenetre(fenetre))
        curseur = _chercher(fenetre)
        if curseur is not None:
            yield curseur            # Prime Video : la barre est revenue
            return
        rect = _bouton_volume(fenetre)
        if rect is None:
            yield None
            return
        # Netflix : le curseur n existe qu au survol de son bouton.
        souris.poser(((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2))
        yield _curseur_pres_de(fenetre, rect)
    finally:
        souris.revenir()


def trouver(fenetre) -> CurseurVolume | None:
    """Le curseur de volume du lecteur, ou None s il n en expose aucun."""
    with reveler(fenetre) as curseur:
        return curseur


def lire(fenetre) -> int | None:
    """Niveau actuel du lecteur, en pourcentage."""
    with reveler(fenetre) as curseur:
        if curseur is None:
            return None
        valeur = curseur.valeur
        return None if valeur < 0 else int(round(valeur))


# --------------------------------------------------------------------------
# Agir
# --------------------------------------------------------------------------
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


def _appuyer(code: int, fois: int) -> None:
    from core import win_utils

    for _ in range(fois):
        win_utils.press_key(code)
        time.sleep(PAUSE_TOUCHE)
    time.sleep(PAUSE_LECTURE)


def _essayer_gros_pas(curseur: CurseurVolume, monte: bool) -> float:
    """
    Un appui sur Page precedente / Page suivante, pour voir.

    Certains lecteurs y repondent par dix points d un coup (Prime Video),
    d autres l ignorent (Netflix). On ne le tente que la ou les fleches sont
    trop fines, et on ne s en sert que si le curseur a vraiment bouge.
    """
    avant = curseur.valeur
    _appuyer(VK_PAGE_HAUT if monte else VK_PAGE_BAS, 1)
    gagne = abs(curseur.valeur - avant)
    return gagne if gagne >= GAIN_GROS_PAS else 0.0


def regler(fenetre, cible: int) -> int | None:
    """
    Amene le volume du lecteur a `cible` (0-100). Retourne le niveau atteint,
    ou None si la fenetre n expose aucun curseur de volume.
    """
    cible = max(0, min(100, int(cible)))
    with reveler(fenetre) as curseur:
        if curseur is None or curseur.valeur < 0:
            return None
        if not _preparer(fenetre, curseur):
            return None
        return _converger(curseur, cible)


def _converger(curseur: CurseurVolume, cible: int) -> int:
    """
    Approche la cible par salves, en mesurant le pas reel a chaque fois.

    Le pas varie de 1 (Prime Video) a 5 (YouTube, Netflix) selon le lecteur,
    et des appuis se perdent quand on en enchaine beaucoup : on recalcule
    donc l ecart apres chaque salve plutot que de compter a l aveugle.
    """
    pas = PAS_SUPPOSE
    gros_pas = None            # None = pas encore essaye, 0.0 = inutilisable
    for _ in range(SALVES_MAX):
        avant = curseur.valeur
        ecart = cible - avant
        if abs(ecart) <= TOLERANCE:
            break
        monte = ecart > 0

        if gros_pas is None and pas <= PAS_TROP_FIN and abs(ecart) >= ECART_GROS_PAS:
            gros_pas = _essayer_gros_pas(curseur, monte)
            if gros_pas:
                continue       # ca marche : on repart avec le nouvel ecart
        if gros_pas and abs(ecart) >= gros_pas:
            code = VK_PAGE_HAUT if monte else VK_PAGE_BAS
            unite = gros_pas
        else:
            code = VK_HAUT if monte else VK_BAS
            unite = max(pas, 1.0)

        touches = max(1, min(TOUCHES_MAX, int(round(abs(ecart) / unite))))
        _appuyer(code, touches)
        parcouru = abs(curseur.valeur - avant)
        if parcouru < 0.5:
            # Butee atteinte, ou lecteur sourd a cette touche : insister ne
            # servirait qu a marteler le clavier.
            break
        if code in (VK_HAUT, VK_BAS):
            pas = parcouru / touches      # le pas reel du lecteur, mesure
    return int(round(curseur.valeur))


def ajuster(fenetre, delta: int) -> int | None:
    """Monte ou baisse le volume du lecteur de `delta` points."""
    with reveler(fenetre) as curseur:
        if curseur is None or curseur.valeur < 0:
            return None
        if not _preparer(fenetre, curseur):
            return None
        return _converger(curseur, int(round(curseur.valeur)) + int(delta))
