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
import re
import time

log = logging.getLogger(__name__)

PROCESSUS = "claude.exe"

TYPE_BOUTON = 50000
TYPE_CHAMP = 50004
TYPE_TEXTE = 50020
TYPE_DOCUMENT = 50030

# L application decoupe elle-meme la conversation, et le dit a l accessibilite :
# un groupe « Chat messages » contenant des « Message 1 of 2 », chacun termine
# par un bloc « Message actions » (horodatage et boutons). On s appuie sur ce
# decoupage plutot que de deviner ou commence la reponse.
MOTIF_MESSAGE = re.compile(r"^message\s+\d+\s+of\s+\d+$", re.IGNORECASE)
NOM_ACTIONS = "message actions"

# En dessous de cette taille, un texte n est pas affiche : ce sont les annonces
# destinees aux lecteurs d ecran (« Claude responded: ... »), qui mesurent deux
# pixels sur trois et repetent la reponse en la tronquant.
TAILLE_MIN_TEXTE = 6

# U+FFFC remplace les images et les icones dans le texte rendu par
# l accessibilite. Le lire a voix haute ne donnerait rien de bon.
OBJET_INCORPORE = "￼"

# Le champ de saisie s annonce ainsi. Les autres champs de la fenetre -- une
# barre de filtre, par exemple -- portent un nom different.
NOMS_SAISIE = ("prompt", "message", "envoyer un message", "how can i help")

DELAI_ARBRE = 8.0            # le temps que l accessibilite s active
PAUSE_SONDAGE = 0.4
PAUSE_FOCUS = 0.3
PAUSE_BASCULE = 0.8          # le temps que l interface se redessine

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


def _boite(element):
    """Le rectangle d un element, ou None."""
    try:
        r = element.CurrentBoundingRectangle
        return (r.left, r.top, r.right, r.bottom)
    except Exception:
        return None


def _dedans(rect, cadre) -> bool:
    """Le centre du rectangle tombe-t-il dans le cadre ?"""
    x = (rect[0] + rect[2]) // 2
    y = (rect[1] + rect[3]) // 2
    return cadre[0] <= x <= cadre[2] and cadre[1] <= y <= cadre[3]


def _propre(texte: str) -> str:
    """Le texte tel qu on peut le lire a voix haute."""
    return " ".join((texte or "").replace(OBJET_INCORPORE, " ").split())


def messages(cible) -> list:
    """
    Les messages affiches, du plus ancien au plus recent.

    On suit le decoupage annonce par l application. A l interieur d un
    message, deux choses sont ecartees : les textes minuscules, qui sont des
    annonces pour lecteur d ecran et non ce qui est affiche, et le bloc
    « Message actions », qui porte l horodatage -- lire « il y a une minute »
    a la suite de la reponse n apprendrait rien.
    """
    elements = _parcourir(cible)[0]
    messages_vus, actions, textes = [], [], []
    for element, type_controle, nom in elements:
        rect = _boite(element)
        if rect is None:
            continue
        if type_controle == TYPE_TEXTE:
            if (nom and rect[2] - rect[0] >= TAILLE_MIN_TEXTE
                    and rect[3] - rect[1] >= TAILLE_MIN_TEXTE):
                textes.append((rect, nom))
        elif MOTIF_MESSAGE.match(nom or ""):
            messages_vus.append(rect)
        elif (nom or "").strip().lower() == NOM_ACTIONS:
            actions.append(rect)

    messages_vus.sort(key=lambda rect: (rect[1], rect[0]))
    echange = []
    for boite in messages_vus:
        dedans = [(rect, nom) for rect, nom in textes
                  if _dedans(rect, boite)
                  and not any(_dedans(rect, action) for action in actions)]
        dedans.sort(key=lambda couple: (couple[0][1], couple[0][0]))
        contenu = _propre(" ".join(nom for _rect, nom in dedans))
        if contenu:
            echange.append(contenu)
    return echange


def conversation(cible) -> str:
    """Le texte de l echange affiche, un message par paragraphe."""
    echange = messages(cible)
    if echange:
        return "\n\n".join(echange)
    return _document_le_plus_long(cible)


def _document_le_plus_long(cible) -> str:
    """
    Repli : le texte du document le plus long.

    A n employer que si le decoupage en messages n a rien donne. Il ramasse
    aussi la barre laterale -- laquelle est plus longue que l echange
    lui-meme, ce qui a longtemps fait lire la liste des conversations a la
    place de la reponse.
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


def activer(cible, libelle: str, pause: float = PAUSE_BASCULE) -> bool:
    """
    Clique un bouton par son nom, puis laisse l interface se redessiner.

    Le delai n est pas une precaution de confort : l arbre est reconstruit
    apres chaque bascule, et chercher l element suivant trop tot ne trouve
    que l ancien ecran.
    """
    from core import interaction

    element = bouton(cible, libelle)
    if element is None:
        log.debug("Bouton introuvable dans l application Claude : %s", libelle)
        return False
    if not interaction.cliquer(element):
        return False
    time.sleep(pause)
    return True


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
                return _reponse(cible, avant, courant)
        else:
            dernier, stable_depuis = courant, None
    return _reponse(cible, avant, dernier) if dernier else ""


def _reponse(cible, avant: str, courant: str) -> str:
    """
    Ce que Claude vient de repondre.

    Le dernier message, quand l application les distingue : c est juste meme
    si l affichage a ete recompose entre-temps. Sinon, ce qui a ete ajoute.
    """
    echange = messages(cible)
    if echange:
        return echange[-1]
    return _nouveaute(avant, courant)


def _nouveaute(avant: str, apres: str) -> str:
    """Ce qui a ete ajoute au texte, nettoye des blancs multiples."""
    ajout = apres[len(avant):] if apres.startswith(avant) else apres
    return _propre(ajout)
