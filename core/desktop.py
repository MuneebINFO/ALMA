"""
Inspection du bureau Windows : ecrans, fenetres, mise au premier plan.

Sert a cibler une action sur un ecran precis (« mets pause sur l ecran 2 »)
et a retrouver une fenetre deja ouverte (« va sur Netflix » doit reutiliser
l onglet existant plutot que d en ouvrir un nouveau).

Tout passe par ctypes : aucune dependance supplementaire.
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)

try:
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
except Exception:  # pragma: no cover - hors Windows
    user32 = None

MONITOR_DEFAULTTONEAREST = 2

# Navigateurs : leur titre de fenetre reflete l onglet actif.
NAVIGATEURS = ("chrome.exe", "firefox.exe", "msedge.exe", "brave.exe",
               "opera.exe", "vivaldi.exe", "librewolf.exe")

# Applications de lecture connues, utile pour deviner « ce qui joue ».
LECTEURS = ("spotify.exe", "vlc.exe", "wmplayer.exe", "musicbee.exe",
            "foobar2000.exe", "itunes.exe", "deezer.exe", "aimp.exe")


@dataclass
class Ecran:
    """Un moniteur, numerote de gauche a droite puis de haut en bas."""

    index: int
    rect: tuple            # (gauche, haut, droite, bas)
    handle: int

    @property
    def largeur(self) -> int:
        return self.rect[2] - self.rect[0]

    @property
    def hauteur(self) -> int:
        return self.rect[3] - self.rect[1]

    def __str__(self) -> str:
        return "écran " + str(self.index) + " (" + str(self.largeur) + "x" + str(self.hauteur) + ")"


@dataclass
class Fenetre:
    """Une fenetre visible, avec l ecran qui l affiche."""

    handle: int
    titre: str
    processus: str
    ecran: int

    @property
    def est_navigateur(self) -> bool:
        return self.processus.lower() in NAVIGATEURS

    @property
    def est_lecteur(self) -> bool:
        return self.processus.lower() in LECTEURS


def ecrans() -> list:
    """
    Liste les moniteurs, numerotes de facon stable : de gauche a droite,
    puis de haut en bas. L ecran 1 est celui le plus a gauche.
    """
    if user32 is None:
        return []
    trouves = []
    proto = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(wintypes.RECT), ctypes.c_double,
    )

    def rappel(handle, _hdc, lprect, _data):
        r = lprect.contents
        trouves.append((handle, (r.left, r.top, r.right, r.bottom)))
        return 1

    try:
        user32.EnumDisplayMonitors(0, 0, proto(rappel), 0)
    except Exception as exc:
        log.debug("Enumeration des ecrans impossible : %s", exc)
        return []

    trouves.sort(key=lambda item: (item[1][0], item[1][1]))
    return [Ecran(i, rect, handle) for i, (handle, rect) in enumerate(trouves, start=1)]


def _nom_processus(hwnd) -> str:
    """Nom du processus proprietaire d une fenetre."""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        import psutil

        return psutil.Process(pid.value).name()
    except Exception:
        return ""


def fenetres(visibles_seulement: bool = True) -> list:
    """Liste les fenetres de premier niveau, avec leur ecran."""
    if user32 is None:
        return []
    liste_ecrans = ecrans()
    index_par_handle = {e.handle: e.index for e in liste_ecrans}
    resultat = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))

    def rappel(hwnd, _lparam):
        if visibles_seulement and not user32.IsWindowVisible(hwnd):
            return True
        longueur = user32.GetWindowTextLengthW(hwnd)
        if longueur == 0:
            return True
        tampon = ctypes.create_unicode_buffer(longueur + 1)
        user32.GetWindowTextW(hwnd, tampon, longueur + 1)
        titre = tampon.value
        if titre in ("Program Manager", "Windows Input Experience"):
            return True
        handle_ecran = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        resultat.append(
            Fenetre(hwnd, titre, _nom_processus(hwnd), index_par_handle.get(handle_ecran, 0))
        )
        return True

    try:
        user32.EnumWindows(proto(rappel), None)
    except Exception as exc:
        log.debug("Enumeration des fenetres impossible : %s", exc)
    return resultat


def fenetres_sur_ecran(index: int) -> list:
    """Fenetres affichees sur l ecran demande."""
    return [f for f in fenetres() if f.ecran == index]


def mettre_au_premier_plan(hwnd) -> bool:
    """
    Affiche une fenetre et lui donne le focus.

    Windows refuse SetForegroundWindow a un processus qui n a pas le focus :
    on rattache brievement notre file d entree a celle de la fenetre visee,
    ce qui est la parade habituelle.
    """
    if user32 is None:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)          # SW_RESTORE
        fil_cible = user32.GetWindowThreadProcessId(hwnd, None)
        fil_courant = ctypes.windll.kernel32.GetCurrentThreadId()
        user32.AttachThreadInput(fil_courant, fil_cible, True)
        try:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            user32.AttachThreadInput(fil_courant, fil_cible, False)
        return user32.GetForegroundWindow() == hwnd
    except Exception as exc:
        log.debug("Mise au premier plan impossible : %s", exc)
        return False


def naviguer_dans_fenetre(fenetre: Fenetre, url: str) -> bool:
    """
    Fait naviguer l onglet ACTIF d une fenetre de navigateur vers une URL.

    On met la fenetre au premier plan, on ouvre la barre d adresse (Ctrl+L)
    puis on colle l URL. Cela reutilise l onglet existant au lieu d en ouvrir
    un nouveau, et cela reste dans le navigateur ou le site est deja ouvert
    (et non dans le navigateur par defaut).
    """
    from core import win_utils

    if not mettre_au_premier_plan(fenetre.handle):
        return False
    import time

    time.sleep(0.25)                       # laisser le focus s etablir
    if not win_utils.press_combo(win_utils.VK_CONTROL, win_utils.VK_L):
        return False
    time.sleep(0.15)
    if not win_utils.type_text(url):
        return False
    time.sleep(0.15)
    return win_utils.press_key(win_utils.VK_RETURN)


def trouver_fenetre(termes, navigateurs_seulement: bool = False):
    """
    Cherche une fenetre dont le titre contient tous les termes donnes.

    Sert a retrouver un site deja ouvert : le titre d une fenetre de
    navigateur reflete son onglet ACTIF, donc un titre qui mentionne Netflix
    signifie que l onglet Netflix est bien celui affiche.
    """
    from core import text_utils

    if isinstance(termes, str):
        termes = [termes]
    termes = [text_utils.normalize(t).strip() for t in termes if t]
    if not termes:
        return None
    for fenetre in fenetres():
        if navigateurs_seulement and not fenetre.est_navigateur:
            continue
        titre = text_utils.normalize(fenetre.titre)
        if all(terme in titre for terme in termes):
            return fenetre
    return None
