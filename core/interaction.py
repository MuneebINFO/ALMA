"""
Interaction avec la page affichee : defilement continu et clic sur un element.

Le defilement tourne dans un thread : la commande rend la main immediatement
et l assistant reste a l ecoute pour pouvoir l arreter.

Le clic passe par UI Automation, qui expose le nom et la position de chaque
element de la page. On privilegie l activation directe de l element (comme le
ferait un lecteur d ecran) et on ne bouge la souris qu en dernier recours.
"""

from __future__ import annotations

import ctypes
import logging
import threading
import time

log = logging.getLogger(__name__)

try:
    user32 = ctypes.windll.user32
except Exception:  # pragma: no cover - hors Windows
    user32 = None

CRAN_MOLETTE = 120          # WHEEL_DELTA
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

BAS = -1
HAUT = 1


def position_souris() -> tuple:
    """Position actuelle du curseur."""
    point = ctypes.wintypes.POINT() if hasattr(ctypes, "wintypes") else None
    from ctypes import wintypes

    point = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def deplacer_souris(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def _molette(crans: int) -> None:
    user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(crans * CRAN_MOLETTE), 0)


def centre(rect: tuple) -> tuple:
    """Centre d un rectangle (gauche, haut, droite, bas)."""
    return (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2


class Defilement:
    """
    Defilement continu d une fenetre, jusqu a ce qu on l arrete.

    La molette est dirigee vers la fenetre SOUS LE CURSEUR : on place donc le
    curseur au centre de la fenetre visee, puis on le remet ou il etait une
    fois termine.
    """

    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.direction = BAS
        self.cible = None

    @property
    def actif(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def demarrer(self, fenetre=None, direction: int = BAS,
                 crans: int = 1, intervalle: float = 0.25,
                 duree_max: float = 300.0) -> bool:
        """
        Lance le defilement.

        Vitesse par defaut mesuree a environ 365 pixels par seconde : de quoi
        parcourir une page en lisant. Deux crans par tic montent deja a plus
        de 1300 px/s, ce qui est illisible.
        """
        if user32 is None:
            return False
        self.arreter()
        self.direction = direction
        self.cible = fenetre
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._boucle, args=(fenetre, direction, crans, intervalle, duree_max),
            daemon=True, name="alma-defilement",
        )
        self._thread.start()
        return True

    def _motif_defilement(self, fenetre):
        """
        Motif de defilement expose par la page, s il existe.

        C est la meilleure methode : elle ne deplace pas le curseur et
        fonctionne meme si la fenetre n a pas le focus. Certaines pages
        (les fils video plein ecran, par exemple) n en exposent pas : on
        retombe alors sur la molette.
        """
        from core import browser_tabs

        uia, module = browser_tabs._client()
        if uia is None or fenetre is None:
            return None
        try:
            racine = uia.ElementFromHandle(fenetre.handle)
            condition = uia.CreatePropertyCondition(
                module.UIA_IsScrollPatternAvailablePropertyId, True
            )
            trouves = racine.FindAll(module.TreeScope_Descendants, condition)
            for index in range(trouves.Length):
                motif = trouves.GetElement(index).GetCurrentPattern(module.UIA_ScrollPatternId)
                concret = motif.QueryInterface(module.IUIAutomationScrollPattern)
                if concret.CurrentVerticallyScrollable:
                    return concret, module
        except Exception as exc:
            log.debug("Motif de defilement introuvable : %s", exc)
        return None

    def _boucle(self, fenetre, direction, crans, intervalle, duree_max) -> None:
        """
        La molette est la methode principale : mesuree a environ 365 px/s
        avec les reglages par defaut, soit une vitesse de lecture confortable.
        Le motif d accessibilite, lui, avance par increments minuscules sur
        les pages longues -- il ne sert que si la molette est indisponible.
        """
        if fenetre is not None and user32 is not None:
            self._boucle_molette(fenetre, direction, crans, intervalle, duree_max)
            return
        trouve = self._motif_defilement(fenetre)
        if trouve is not None:
            self._boucle_accessibilite(trouve, direction, crans, intervalle, duree_max)

    def _boucle_accessibilite(self, trouve, direction, crans, intervalle, duree_max) -> None:
        """Defilement par le motif de la page : rien ne bouge a l ecran."""
        motif, module = trouve
        pas = (module.ScrollAmount_SmallDecrement if direction == HAUT
               else module.ScrollAmount_SmallIncrement)
        fin = time.monotonic() + duree_max
        while not self._stop.is_set() and time.monotonic() < fin:
            try:
                for _ in range(max(1, crans)):
                    motif.Scroll(module.ScrollAmount_NoAmount, pas)
            except Exception as exc:
                log.debug("Defilement interrompu : %s", exc)
                return
            self._stop.wait(intervalle)

    def _boucle_molette(self, fenetre, direction, crans, intervalle, duree_max) -> None:
        """
        Repli : molette de souris. Elle vise la fenetre SOUS LE CURSEUR, on
        deplace donc le curseur au centre de la fenetre puis on le remet.
        """
        depart = position_souris()
        deplace = False
        try:
            if fenetre is not None:
                from core import desktop

                desktop.mettre_au_premier_plan(fenetre.handle)
                rect = _rectangle_fenetre(fenetre.handle)
                if rect:
                    deplacer_souris(*centre(rect))
                    deplace = True
                    time.sleep(0.15)
            fin = time.monotonic() + duree_max
            while not self._stop.is_set() and time.monotonic() < fin:
                _molette(direction * crans)
                self._stop.wait(intervalle)
        except Exception as exc:
            log.debug("Defilement interrompu : %s", exc)
        finally:
            if deplace:
                try:
                    deplacer_souris(*depart)
                except Exception:
                    pass

    def arreter(self) -> bool:
        """Arrete le defilement en cours. True s il y en avait un."""
        if not self.actif:
            return False
        self._stop.set()
        self._thread.join(timeout=2)
        return True


def _rectangle_fenetre(handle) -> tuple | None:
    """Rectangle ecran d une fenetre."""
    try:
        from ctypes import wintypes

        rect = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return None
        return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        return None


# --------------------------------------------------------------------------
# Clic sur un element de la page
# --------------------------------------------------------------------------
# Identifiants de types UI Automation.
BOUTON = 50000
CASE = 50002
CHAMP = 50004
LIEN = 50005
IMAGE = 50006
ITEM_LISTE = 50007
ONGLET = 50019
GROUPE = 50026
VOLET = 50033

# Types sur lesquels un clic a du sens.
TYPES_CLIQUABLES = (BOUTON, CASE, LIEN, IMAGE, ITEM_LISTE, ONGLET, GROUPE, VOLET)


class Cible:
    """Un element cliquable de la page."""

    def __init__(self, nom: str, rect: tuple, element, type_controle: int = 0) -> None:
        self.nom = nom
        self.rect = rect
        self.element = element
        self.type_controle = type_controle

    @property
    def surface(self) -> int:
        return max(0, self.rect[2] - self.rect[0]) * max(0, self.rect[3] - self.rect[1])

    def __repr__(self) -> str:
        return "Cible(" + self.nom[:40] + ")"


def _visible_dans(rect: tuple, zone: tuple) -> bool:
    """Le rectangle est-il reellement affiche dans la fenetre ?"""
    return not (rect[2] <= zone[0] or rect[0] >= zone[2]
                or rect[3] <= zone[1] or rect[1] >= zone[3])


def elements_cliquables(fenetre, taille_min: int = 12,
                        visibles_seulement: bool = True) -> list:
    """
    Liste les elements nommes d une fenetre, en ordre de lecture (de haut en
    bas, puis de gauche a droite).

    Par defaut on ne garde que ce qui est REELLEMENT a l ecran : la page
    contient aussi tout ce qui a defile hors champ, et cliquer physiquement
    sur un tel element taperait a cote.
    """
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if uia is None:
        return []
    zone = _rectangle_fenetre(fenetre.handle) if visibles_seulement else None
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        tous = racine.FindAll(module.TreeScope_Descendants, uia.CreateTrueCondition())
    except Exception as exc:
        log.debug("Lecture des elements impossible : %s", exc)
        return []

    cibles = []
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            nom = (element.CurrentName or "").strip()
            if not nom or element.CurrentControlType not in TYPES_CLIQUABLES:
                continue
            r = element.CurrentBoundingRectangle
            rect = (r.left, r.top, r.right, r.bottom)
            if rect[2] - rect[0] < taille_min or rect[3] - rect[1] < taille_min:
                continue
            if zone is not None and not _visible_dans(rect, zone):
                continue
            cible = Cible(nom, rect, element, element.CurrentControlType)
            cible.fenetre = fenetre
            cibles.append(cible)
        except Exception:
            continue
    cibles.sort(key=lambda c: (c.rect[1], c.rect[0]))
    return cibles


def _activer(cible: Cible) -> bool:
    """
    Active un element sans toucher a la souris, comme le ferait un lecteur
    d ecran. Retourne False si l element n expose pas d action.
    """
    from core import browser_tabs

    _uia, module = browser_tabs._client()
    if module is None:
        return False
    for id_motif, interface, methode in (
        (module.UIA_InvokePatternId, "IUIAutomationInvokePattern", "Invoke"),
        (module.UIA_LegacyIAccessiblePatternId, "IUIAutomationLegacyIAccessiblePattern",
         "DoDefaultAction"),
    ):
        try:
            motif = cible.element.GetCurrentPattern(id_motif)
            if not motif:
                continue
            concret = motif.QueryInterface(getattr(module, interface))
            getattr(concret, methode)()
            return True
        except Exception:
            continue
    return False


def _clic_physique(cible: Cible, restaurer: bool = True) -> bool:
    """Dernier recours : deplacer la souris sur l element et cliquer."""
    if user32 is None:
        return False
    depart = position_souris()
    try:
        deplacer_souris(*centre(cible.rect))
        time.sleep(0.12)
        user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        return True
    except Exception as exc:
        log.debug("Clic impossible : %s", exc)
        return False
    finally:
        if restaurer:
            time.sleep(0.25)
            try:
                deplacer_souris(*depart)
            except Exception:
                pass


def cliquer(cible: Cible) -> bool:
    """Active l element, avec repli sur un clic reel."""
    from core import desktop

    if _activer(cible):
        return True
    fenetre = getattr(cible, "fenetre", None)
    if fenetre is not None:
        desktop.mettre_au_premier_plan(fenetre.handle)
    return _clic_physique(cible)


def chercher_cible(cibles: list, termes: str, types=None):
    """
    Retrouve l element correspondant a ce que l utilisateur a nomme.

    On prefere la correspondance la plus courte : « Damso » doit viser le
    lien « Damso » plutot qu un titre de 80 caracteres qui le contient.

    `types` restreint la recherche a certaines natures d elements (« le
    bouton lecture » ne doit pas tomber sur un titre de video). Si rien n est
    trouve dans ces types, on elargit plutot que de repondre bredouille.
    """
    from core import text_utils

    voulu = text_utils.normalize(termes).strip()
    if not voulu:
        return None
    if types:
        restreint = [c for c in cibles if c.type_controle in types]
        trouve = chercher_cible(restreint, termes) if restreint else None
        if trouve is not None:
            return trouve
    exacts, partiels = [], []
    for cible in cibles:
        nom = text_utils.normalize(cible.nom).strip()
        if nom == voulu:
            exacts.append(cible)
        elif voulu in nom:
            partiels.append(cible)
    if exacts:
        return exacts[0]
    if partiels:
        return min(partiels, key=lambda c: len(c.nom))
    # Dernier essai : tolerance aux erreurs de transcription.
    noms = [c.nom for c in cibles]
    meilleur = text_utils.best_match(voulu, noms, threshold=0.72)
    return next((c for c in cibles if c.nom == meilleur), None) if meilleur else None
