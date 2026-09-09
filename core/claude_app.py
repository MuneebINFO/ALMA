"""
Pilotage de l application Claude installee sur la machine.

Elle est ecrite en Electron, et cela change tout : au repos elle n expose
QUATORZE elements -- les boutons de la fenetre, rien d autre. Chromium
n active son arbre d accessibilite que lorsqu un client s y attache et que la
fenetre passe devant. On mesure alors 531 elements, dont le champ de saisie
et la conversation. D ou la premiere chose que fait ce module : mettre la
fenetre au premier plan, puis attendre que l arbre se remplisse.

Le reste suit le meme principe que partout ailleurs dans le projet : on lit
par l API d accessibilite, on ecrit au clavier. Ecrire la valeur du champ
serait ignore -- c est un editeur riche, pas un <input>.

Rien ici ne passe par une API : c est l application deja installee et deja
connectee qui travaille, avec l abonnement de l utilisateur.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

PROCESSUS = "claude.exe"

TYPE_BOUTON = 50000
TYPE_CHAMP = 50004
TYPE_DOCUMENT = 50030

# Le champ de saisie s annonce ainsi. Les autres champs de la fenetre -- une
# barre de filtre, par exemple -- portent un nom different.
NOMS_SAISIE = ("prompt", "message", "envoyer un message", "how can i help")

DELAI_ARBRE = 8.0            # le temps que l accessibilite s active
PAUSE_SONDAGE = 0.4
PAUSE_FOCUS = 0.3

# Une reponse s ecrit mot a mot : on la considere finie quand le texte cesse
# de grandir pendant assez longtemps.
STABILITE_REQUISE = 2.0
DELAI_REPONSE = 90.0


def fenetre():
    """La fenetre de l application Claude, ou None."""
    from core import desktop

    for candidate in desktop.fenetres():
        if candidate.processus.lower() == PROCESSUS:
            return candidate
    return None


def _elements(cible):
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if uia is None:
        return None, None
    try:
        racine = uia.ElementFromHandle(cible.handle)
        return racine.FindAll(module.TreeScope_Descendants,
                              uia.CreateTrueCondition()), module
    except Exception as exc:
        log.debug("Arbre illisible : %s", exc)
        return None, None


def reveiller(cible, delai: float = DELAI_ARBRE) -> bool:
    """
    Amene la fenetre devant et attend que son arbre se remplisse.

    Sans cela on ne voit que la barre de titre : Electron ne publie son
    contenu qu une fois la fenetre active et un client d accessibilite
    attache.
    """
    from core import desktop

    desktop.mettre_au_premier_plan(cible.handle)
    fin = time.time() + max(0.0, delai)
    while True:
        tous, _module = _elements(cible)
        if tous is not None and tous.Length > 60:
            return True
        if time.time() >= fin:
            return False
        time.sleep(PAUSE_SONDAGE)


def _parcourir(cible):
    """Les elements exposes, avec leur type et leur nom. Robuste aux perimes."""
    tous, module = _elements(cible)
    if tous is None:
        return [], None
    trouves = []
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            trouves.append((element, element.CurrentControlType,
                            (element.CurrentName or "").strip()))
        except Exception:
            # L interface se redessine pendant qu on la lit : l element
            # disparait, on passe au suivant.
            continue
    return trouves, module


def champ_de_saisie(cible):
    """Le champ où l'on écrit la question, ou None."""
    for element, type_controle, nom in _parcourir(cible)[0]:
        if type_controle != TYPE_CHAMP:
            continue
        if any(mot in nom.lower() for mot in NOMS_SAISIE):
            return element
    return None


def bouton(cible, libelle: str):
    """
    Un bouton ou un onglet dont le nom correspond, au plus proche.

    On garde le rectangle reel de chaque element : si l activation par
    l accessibilite est ignoree -- cela arrive dans une interface web -- le
    repli au clic reel a besoin de savoir ou pointer.
    """
    from core import interaction

    candidats = []
    for element, type_controle, nom in _parcourir(cible)[0]:
        if not nom:
            continue
        try:
            r = element.CurrentBoundingRectangle
            rect = (r.left, r.top, r.right, r.bottom)
        except Exception:
            continue
        if rect[2] - rect[0] < 2 or rect[3] - rect[1] < 2:
            continue  # replie ou hors ecran : rien a cliquer
        objet = interaction.Cible(nom, rect, element, type_controle)
        objet.fenetre = cible
        candidats.append(objet)
    return interaction.chercher_cible(candidats, libelle)


def conversation(cible) -> str:
    """
    Le texte de la conversation affichee.

    On prend le document le plus long : la fenetre en expose plusieurs -- la
    barre laterale, la liste des sessions -- et c est l echange en cours qui
    nous interesse.
    """
    elements, module = _parcourir(cible)
    if module is None:
        return ""
    meilleur = ""
    for element, type_controle, _nom in elements:
        if type_controle != TYPE_DOCUMENT:
            continue
        try:
            motif = element.GetCurrentPattern(module.UIA_TextPatternId)
            if not motif:
                continue
            texte = motif.QueryInterface(module.IUIAutomationTextPattern) \
                         .DocumentRange.GetText(-1)
        except Exception:
            continue
        if texte and len(texte) > len(meilleur):
            meilleur = texte
    return meilleur


def poser(cible, question: str) -> bool:
    """Écrit la question dans le champ de saisie et l envoie."""
    from core import interaction, win_utils

    champ = champ_de_saisie(cible)
    if champ is None:
        return False
    try:
        champ.SetFocus()
    except Exception as exc:
        log.debug("Focus du champ impossible : %s", exc)
        return False
    time.sleep(PAUSE_FOCUS)
    # Le champ peut contenir un brouillon : on le remplace plutot que de s y
    # ajouter, sinon la question part collee a autre chose.
    win_utils.press_combo(win_utils.VK_CONTROL, ord("A"))
    time.sleep(0.1)
    if not win_utils.type_text(question):
        return False
    time.sleep(0.25)
    return win_utils.press_key(win_utils.VK_RETURN)


def attendre_la_reponse(cible, avant: str, delai: float = DELAI_REPONSE) -> str:
    """
    Attend que la reponse cesse de s ecrire, puis rend ce qui a ete ajoute.

    L application ne signale nulle part qu elle a fini. On guette donc la
    STABILITE du texte : tant qu il grandit, elle parle encore.
    """
    fin = time.time() + max(0.0, delai)
    dernier, stable_depuis = "", None
    while time.time() < fin:
        time.sleep(PAUSE_SONDAGE)
        courant = conversation(cible)
        if len(courant) <= len(avant):
            continue
        if courant == dernier:
            if stable_depuis is None:
                stable_depuis = time.time()
            elif time.time() - stable_depuis >= STABILITE_REQUISE:
                return _nouveaute(avant, courant)
        else:
            dernier, stable_depuis = courant, None
    return _nouveaute(avant, dernier) if dernier else ""


def _nouveaute(avant: str, apres: str) -> str:
    """Ce qui a ete ajoute au texte, nettoye des blancs multiples."""
    ajout = apres[len(avant):] if apres.startswith(avant) else apres
    return " ".join(ajout.split())
