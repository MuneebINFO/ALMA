"""
Inspection du bureau Windows : ecrans, fenetres, mise au premier plan.

Sert a cibler une action sur un ecran precis (« mets pause sur l ecran 2 »)
et a retrouver une fenetre deja ouverte (« va sur Netflix » doit reutiliser
l onglet existant plutot que d en ouvrir un nouveau).

Tout passe par ctypes : aucune dependance supplementaire.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import time
from ctypes import wintypes
from dataclasses import dataclass

log = logging.getLogger(__name__)

try:
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
except Exception:  # pragma: no cover - hors Windows
    user32 = None

MONITOR_DEFAULTTONEAREST = 2

# DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
CONTEXTE_PAR_MONITEUR = -4

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


@contextlib.contextmanager
def dpi_par_moniteur():
    """
    Bascule le thread courant en conscience DPI « par moniteur ».

    Le processus est seulement « system aware » : Windows lui presente les
    ecrans dont l echelle differe de celle de l ecran principal avec des
    coordonnees redimensionnees, et redimensionne a son tour les fenetres
    qu on y place. Un ecran a 100 % voisin d un ecran principal a 125 % est
    ainsi annonce 2400x1350 au lieu de 1920x1080, et une fenetre censee le
    couvrir n en occupe que les deux tiers.

    Dans ce contexte, les coordonnees redeviennent des pixels physiques.
    Les fenetres creees ici gardent ce comportement pour toute leur vie ;
    le reste de l application n est pas affecte.
    """
    precedent = None
    if user32 is not None:
        try:
            user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
            user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
            precedent = user32.SetThreadDpiAwarenessContext(
                ctypes.c_void_p(CONTEXTE_PAR_MONITEUR))
        except Exception as exc:  # Windows 8.1 et anterieurs
            log.debug("Contexte DPI par moniteur indisponible : %s", exc)
            precedent = None
    try:
        yield bool(precedent)
    finally:
        if precedent:
            try:
                user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(precedent))
            except Exception as exc:
                log.debug("Restauration du contexte DPI impossible : %s", exc)


def ecrans_physiques() -> list:
    """Les ecrans avec leurs vraies coordonnees en pixels, sans mise a l echelle."""
    with dpi_par_moniteur():
        return ecrans()


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


VK_ALT = 0x12
KEYEVENTF_KEYUP = 0x0002
DELAI_PREMIER_PLAN = 0.35


def _essayer_devant(hwnd) -> None:
    """
    Une tentative de passage au premier plan, file d entree rattachee.

    Windows refuse SetForegroundWindow a un processus qui n a pas deja le
    focus. La parade consiste a rattacher brievement notre file d entree a
    celle de la fenetre QUI EST DEVANT -- c est elle qui detient le droit, pas
    la fenetre visee. S y rattacher a la place ne donne rien, et « va sur
    Chrome » depuis une autre application echouait a tous les coups.
    """
    devant = user32.GetForegroundWindow()
    fil_devant = user32.GetWindowThreadProcessId(devant, None) if devant else 0
    fil_courant = ctypes.windll.kernel32.GetCurrentThreadId()
    rattache = bool(fil_devant) and fil_devant != fil_courant
    if rattache:
        user32.AttachThreadInput(fil_courant, fil_devant, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if rattache:
            user32.AttachThreadInput(fil_courant, fil_devant, False)


def mettre_au_premier_plan(hwnd) -> bool:
    """
    Affiche une fenetre et lui donne le focus.

    Deux tentatives, car Windows protege le premier plan : une fois la file
    d entree rattachee, puis -- si cela n a pas suffi -- apres une pression sur
    ALT, qui rend a notre processus le droit de changer le premier plan.
    """
    if user32 is None:
        return False
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        if user32.GetForegroundWindow() == hwnd:
            return True

        _essayer_devant(hwnd)
        if _attendre_le_premier_plan(hwnd):
            return True

        # Le verrou du premier plan se leve pour le processus qui vient de
        # recevoir une entree clavier. ALT seul ne declenche rien ailleurs.
        user32.keybd_event(VK_ALT, 0, 0, 0)
        user32.keybd_event(VK_ALT, 0, KEYEVENTF_KEYUP, 0)
        _essayer_devant(hwnd)
        return _attendre_le_premier_plan(hwnd)
    except Exception as exc:
        log.debug("Mise au premier plan impossible : %s", exc)
        return False


def _attendre_le_premier_plan(hwnd, delai: float = DELAI_PREMIER_PLAN) -> bool:
    """
    Le changement de premier plan n est pas instantane.

    Interroger GetForegroundWindow dans la foulee repond « non » alors que la
    fenetre arrive : on laisse le temps a l affichage de suivre.
    """
    fin = time.time() + delai
    while True:
        if user32.GetForegroundWindow() == hwnd:
            return True
        if time.time() >= fin:
            return False
        time.sleep(0.03)


SW_RESTORE = 9
SW_MAXIMISER = 3
SWP_SANS_ORDRE = 0x0004
SWP_SANS_ACTIVER = 0x0010
MARGE_ECRAN = 60          # on ne colle pas la fenetre aux bords


def poignees_visibles() -> set:
    """Les fenetres visibles a cet instant, pour reperer celles qui arrivent."""
    return {f.handle for f in fenetres()}


# Fenetres de passage : beaucoup de lanceurs sont des scripts, et la console
# qui les execute apparait avant l application. La deplacer a la place de
# l application serait la seule chose visible du travail demande.
PROCESSUS_DE_PASSAGE = ("cmd.exe", "conhost.exe", "powershell.exe",
                        "windowsterminal.exe", "openconsole.exe", "pwsh.exe")


def attendre_nouvelle_fenetre(connues: set, delai: float = 12.0,
                              processus: str = "") -> Fenetre | None:
    """
    Attend qu une fenetre inconnue apparaisse. Retourne la fenetre, ou None.

    Une application met du temps a s afficher, et certaines ouvrent d abord
    une console ou un ecran de demarrage : on prend la premiere fenetre
    nommee qui n etait pas la avant, en laissant passer les consoles -- sauf
    si c est justement une console qu on a demandee.
    """
    import time

    attendu = (processus or "").lower()
    fin = time.time() + delai
    while time.time() < fin:
        for fenetre in fenetres():
            if fenetre.handle in connues or not fenetre.titre.strip():
                continue
            nom = fenetre.processus.lower()
            if attendu:
                if attendu not in nom:
                    continue
            elif nom in PROCESSUS_DE_PASSAGE:
                continue
            return fenetre
        time.sleep(0.25)
    return None


def deplacer_vers_ecran(handle, index: int) -> bool:
    """
    Deplace une fenetre sur l ecran demande, en gardant sa taille.

    Une fenetre agrandie doit d abord etre restauree : agrandie, elle est
    collee a son ecran et refuse de bouger. On la ragrandit ensuite, sur le
    nouvel ecran cette fois.
    """
    if user32 is None:
        return False
    cible = next((e for e in ecrans() if e.index == index), None)
    if cible is None:
        return False
    try:
        agrandie = bool(user32.IsZoomed(handle))
        if agrandie:
            user32.ShowWindow(handle, SW_RESTORE)
            import time

            time.sleep(0.25)
        rect = wintypes.RECT()
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            return False
        largeur = min(rect.right - rect.left, cible.largeur - MARGE_ECRAN)
        hauteur = min(rect.bottom - rect.top, cible.hauteur - MARGE_ECRAN)
        largeur = max(largeur, 320)
        hauteur = max(hauteur, 240)
        gauche = cible.rect[0] + (cible.largeur - largeur) // 2
        haut = cible.rect[1] + (cible.hauteur - hauteur) // 2
        user32.SetWindowPos(handle, 0, gauche, haut, largeur, hauteur,
                            SWP_SANS_ORDRE | SWP_SANS_ACTIVER)
        if agrandie:
            user32.ShowWindow(handle, SW_MAXIMISER)
        return True
    except Exception as exc:
        log.debug("Deplacement de fenetre impossible : %s", exc)
        return False


def ouvrir_onglet(fenetre: Fenetre, url: str) -> bool:
    """
    Ouvre un NOUVEL onglet sur une adresse, dans cette fenetre de navigateur.

    Passer par le navigateur par defaut ouvrirait souvent une fenetre de
    plus ; ici on reste dans celle qui est deja la : Ctrl+T, l adresse,
    Entree -- exactement ce que ferait l utilisateur.
    """
    from core import win_utils

    if not mettre_au_premier_plan(fenetre.handle):
        return False
    import time

    time.sleep(0.25)
    if not win_utils.press_combo(win_utils.VK_CONTROL, ord("T")):
        return False
    time.sleep(0.35)                       # l onglet doit exister avant qu on ecrive
    if not win_utils.type_text(url):
        return False
    time.sleep(0.15)
    return win_utils.press_key(win_utils.VK_RETURN)


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


def trouver_fenetre(termes, navigateurs_seulement: bool = False, ecran: int | None = None):
    """
    Cherche une fenetre dont le titre contient tous les termes donnes.

    Sert a retrouver un site deja ouvert : le titre d une fenetre de
    navigateur reflete son onglet ACTIF, donc un titre qui mentionne Netflix
    signifie que l onglet Netflix est bien celui affiche.

    `ecran` privilegie les fenetres affichees sur cet ecran, sans s y
    enfermer : si le site n y est pas, on le cherche ailleurs plutot que de
    repondre qu il n existe pas.
    """
    from core import text_utils

    if isinstance(termes, str):
        termes = [termes]
    termes = [text_utils.normalize(t).strip() for t in termes if t]
    if not termes:
        return None

    candidates = []
    for fenetre in fenetres():
        if navigateurs_seulement and not fenetre.est_navigateur:
            continue
        titre = text_utils.normalize(fenetre.titre)
        if all(terme in titre for terme in termes):
            candidates.append(fenetre)
    if not candidates:
        return None
    if ecran is not None:
        for fenetre in candidates:
            if fenetre.ecran == ecran:
                return fenetre
    return candidates[0]
