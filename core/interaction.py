"""
Interaction avec la page affichee : defilement continu et clic sur un element.

Le defilement tourne dans un thread : la commande rend la main immediatement
et l assistant reste a l ecoute pour pouvoir l arreter.

Le clic passe par UI Automation, qui expose le nom et la position de chaque
element de la page. On privilegie l activation directe de l element (comme le
ferait un lecteur d ecran) et on ne bouge la souris qu en dernier recours.
"""

from __future__ import annotations

import contextlib
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


TYPE_DOCUMENT = 50030          # UIA_DocumentControlTypeId


def zone_page(fenetre):
    """
    Le rectangle de la PAGE, sans l habillage du navigateur.

    Une fenetre de navigateur contient deux mondes : sa propre interface --
    barre d onglets, barre d adresse, favoris -- et la page. Ils se
    ressemblent a s y meprendre pour qui lit l arbre d accessibilite : un
    onglet nomme « Tik Tok - Recherche Google » repond aussi bien a « clique
    sur Tik Tok » que le resultat cherche. Le document, lui, est un element
    a part, et son rectangle delimite exactement la page.

    Retourne None hors navigateur, ou si le document est introuvable.
    """
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if uia is None:
        return None
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        condition = uia.CreatePropertyCondition(module.UIA_ControlTypePropertyId,
                                                TYPE_DOCUMENT)
        documents = racine.FindAll(module.TreeScope_Descendants, condition)
    except Exception as exc:
        log.debug("Zone de page introuvable : %s", exc)
        return None
    zone = None
    for index in range(documents.Length):
        try:
            r = documents.GetElement(index).CurrentBoundingRectangle
            if r.right <= r.left or r.bottom <= r.top:
                continue
            rect = (r.left, r.top, r.right, r.bottom)
            zone = rect if zone is None else (
                min(zone[0], rect[0]), min(zone[1], rect[1]),
                max(zone[2], rect[2]), max(zone[3], rect[3]),
            )
        except Exception:
            continue
    return zone


MARGE_PAGE = 4          # tolerance de bordure, en pixels


def _dans(rect: tuple, zone: tuple) -> bool:
    """
    Le rectangle tient-il ENTIEREMENT dans la zone ?

    Le centre ne suffit pas : une fenetre de navigateur contient un volet
    qui la couvre en entier et porte le titre de la page. Son centre tombe
    dans la page, mais il deborde sur la barre d onglets -- et cliquer
    dessus ne fait rien. Exiger l inclusion l ecarte, avec tous les autres
    conteneurs, sans toucher au contenu.
    """
    return (rect[0] >= zone[0] - MARGE_PAGE
            and rect[1] >= zone[1] - MARGE_PAGE
            and rect[2] <= zone[2] + MARGE_PAGE
            and rect[3] <= zone[3] + MARGE_PAGE)


def elements_cliquables(fenetre, taille_min: int = 12,
                        visibles_seulement: bool = True,
                        page_seulement: bool = False) -> list:
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
    # Restreindre a la page ecarte d un coup les onglets, la barre d adresse
    # et les favoris, qui portent souvent les memes mots que ce qu on cherche.
    page = zone_page(fenetre) if page_seulement else None
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
            if page is not None and not _dans(rect, page):
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


def cliquer(cible: Cible, physique: bool = False) -> bool:
    """
    Active l element, avec repli sur un clic reel.

    `physique` force d emblee le clic a la souris. L activation par l API
    d accessibilite est plus propre -- elle ne bouge pas le pointeur -- mais
    une page peut l accepter sans rien en faire : elle repond alors « c est
    fait » alors que rien n a bouge. Quand l appelant sait verifier l effet,
    il peut donc redemander un vrai clic.
    """
    from core import desktop

    if not physique and _activer(cible):
        return True
    fenetre = getattr(cible, "fenetre", None)
    if fenetre is not None:
        desktop.mettre_au_premier_plan(fenetre.handle)
    return _clic_physique(cible)


# --------------------------------------------------------------------------
# Reveiller les controles qui se cachent
# --------------------------------------------------------------------------
PAUSE_REVEIL = 0.35


def centre_fenetre(fenetre):
    """Centre d une fenetre, en pixels ecran, ou None."""
    try:
        from ctypes import wintypes

        rect = wintypes.RECT()
        if not user32.GetWindowRect(fenetre.handle, ctypes.byref(rect)):
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
    except Exception as exc:
        log.debug("Rectangle de la fenetre inconnu : %s", exc)
        return None


class Souris:
    """Deplace le pointeur et retient d ou il vient, pour l y remettre."""

    def __init__(self):
        try:
            self.depart = position_souris()
        except Exception:
            self.depart = None

    def poser(self, point) -> bool:
        """Amene le pointeur sur un point, avec un vrai mouvement."""
        if point is None:
            return False
        try:
            # Deux deplacements : un saut unique peut ne declencher aucun
            # evenement de survol et ne rien reveiller.
            deplacer_souris(point[0], point[1])
            time.sleep(0.12)
            deplacer_souris(point[0] + 3, point[1] + 1)
            time.sleep(PAUSE_REVEIL)
            return True
        except Exception as exc:
            log.debug("Deplacement du pointeur impossible : %s", exc)
            return False

    def revenir(self) -> None:
        if self.depart is None:
            return
        try:
            deplacer_souris(*self.depart)
        except Exception:
            pass


@contextlib.contextmanager
def controles_reveilles(fenetre):
    """
    Fait apparaitre les controles qui se cachent, et les y maintient.

    Un lecteur video referme sa barre de controle apres quelques secondes et
    la retire de l arbre d accessibilite : ses boutons n existent alors plus
    du tout. Mesure sur le lecteur Netflix : zero element de contenu au
    repos, neuf apres un mouvement de souris. Le pointeur doit rester la
    jusqu au clic, puis retrouver sa place.
    """
    souris = Souris()
    try:
        yield souris.poser(centre_fenetre(fenetre))
    finally:
        souris.revenir()


# --------------------------------------------------------------------------
# Reconnaissance des titres sur les sites de streaming
# --------------------------------------------------------------------------
# Le nom accessible d une vignette n est pas un titre : c est une fiche.
#   « Deadpool & Wolverine Classe 16+ Sortie : 2024. Super-heros, Action... »
#   « Hulu Original Series Malcolm : Rien n a change Classe 12+ Sortie... »
# Le titre est au milieu, entre une etiquette et une avalanche de metadonnees.
# On le degage pour pouvoir comparer ce que l utilisateur a dit a ce qu il
# voit, et non a tout ce que le site a colle autour.
ETIQUETTES = (
    "hulu original series", "hulu original", "hulu generic",
    "disney original series", "disney original", "original series",
    "serie originale", "film original", "nouvelle serie", "nouveau film",
    "nouvel episode", "badge", "recommande", "exclusivite",
    # Selecteurs de profil : « Profil de Muneeb. Selectionnez cette... »
    "profil de", "profil", "profile of", "profile",
)
METADONNEES = (
    "classe ", "classee ", "sortie :", "sortie:", "note :", "duree ",
    "rated ", "released ", "maturity rating", "ans et plus", "tous publics",
    "regarder maintenant", "reprendre la lecture",
    "nouvelle saison", "nouveaux episodes", "tous les episodes",
    "disponible des maintenant", "disponible maintenant",
    "selectionnez cette option", "select this option", "cliquez pour",
)
# Mots que l on ignore quand on compare : ils varient d une formulation a
# l autre (« Deadpool & Wolverine » se dit « Deadpool et Wolverine »).
MOTS_VIDES = {"le", "la", "les", "l", "un", "une", "des", "du", "de", "d",
              "et", "and", "the", "a", "au", "aux", "en", "avec", "pour"}


def titre_visible(nom: str) -> str:
    """
    Le titre seul, degage de l etiquette qui le precede et de la fiche qui le
    suit. Renvoie une chaine normalisee, prete a comparer.
    """
    from core import text_utils

    titre = text_utils.normalize(nom or "").strip()
    for etiquette in ETIQUETTES:
        if titre.startswith(etiquette + " "):
            titre = titre[len(etiquette) + 1:].strip()
            break
    coupures = [titre.find(marqueur) for marqueur in METADONNEES]
    coupures = [c for c in coupures if c > 0]
    if coupures:
        titre = titre[: min(coupures)]
    return titre.strip(" :.-,;").strip()


def titre_affiche(nom: str) -> str:
    """
    Le titre tel qu il est ecrit a l ecran, accents et majuscules compris.

    La normalisation preserve la longueur caractere par caractere : il suffit
    donc de retrouver la position du titre dans la version normalisee pour le
    decouper dans la chaine d origine.
    """
    from core import text_utils

    titre = titre_visible(nom)
    if not titre:
        return nom
    debut = text_utils.normalize(nom).find(titre)
    if debut < 0:
        return nom
    return nom[debut:debut + len(titre)].strip()


def _mots(texte: str) -> list:
    from core import text_utils

    return [m for m in text_utils.tokenize(texte) if m]


def _mots_utiles(texte: str) -> list:
    """Les mots qui portent le sens ; jamais une liste vide."""
    mots = _mots(texte)
    return [m for m in mots if m not in MOTS_VIDES] or mots


# En dessous de ce niveau, la correspondance est litterale : le libelle le
# plus court est alors le plus proche de ce qui a ete demande. Au-dessus,
# elle est approchante, et c est l ordre de lecture qui renseigne le mieux --
# sur une page de resultats, le premier est celui qu on veut.
NIVEAU_APPROCHANT = 3


def _rang(cible, voulu: str, mots_voulus: set, position: int = 0) -> tuple | None:
    """
    A quel point cette cible correspond ? Plus petit est meilleur.

    Du plus sur au plus large : le titre exact, le titre qui contient la
    demande, le nom complet qui la contient, la meme chose une fois les
    espaces retires -- la voix dit « Tik Tok », la page ecrit « TikTok » --
    puis tous les mots presents, ce qui rattrape la ponctuation et les
    esperluettes.
    """
    from core import text_utils

    nom = text_utils.normalize(cible.nom).strip()
    titre = titre_visible(cible.nom)
    if not nom:
        return None
    serre = voulu.replace(" ", "")
    if nom == voulu or titre == voulu:
        niveau = 0
    elif voulu and voulu in titre:
        niveau = 1
    elif voulu and voulu in nom:
        niveau = 2
    elif serre and serre in titre.replace(" ", ""):
        niveau = 3
    elif serre and serre in nom.replace(" ", ""):
        niveau = 4
    elif mots_voulus and mots_voulus <= set(_mots(titre)):
        niveau = 5
    elif mots_voulus and mots_voulus <= set(_mots(nom)):
        niveau = 6
    else:
        return None
    if niveau < NIVEAU_APPROCHANT:
        return (niveau, len(titre) or len(nom), len(nom))
    return (niveau, position, len(nom))


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
    mots_voulus = set(_mots_utiles(voulu))
    classees = []
    for position, cible in enumerate(cibles):
        rang = _rang(cible, voulu, mots_voulus, position)
        if rang is not None:
            classees.append((rang, cible))
    if classees:
        return min(classees, key=lambda paire: paire[0])[1]

    # Dernier essai : tolerance aux erreurs de transcription. On compare au
    # TITRE et non au nom complet, sinon vingt mots de metadonnees noient la
    # ressemblance et plus rien ne depasse le seuil.
    meilleur, ecart = None, 0.0
    for cible in cibles:
        for texte in (titre_visible(cible.nom), text_utils.normalize(cible.nom).strip()):
            score = text_utils.similarity(voulu, texte)
            if score > ecart:
                meilleur, ecart = cible, score
    if ecart >= 0.72:
        return meilleur

    # Ultime recours : la SONORITE. Un nom propre est ce que la reconnaissance
    # vocale rend le plus mal -- « Muneeb » revient en « Mounib », qui ne se
    # ressemble qu a 0,67 en lettres mais s entend pareil. On ne s autorise
    # cette comparaison qu ici, quand plus rien d autre n a repondu.
    from core import deduction

    for cible in cibles:
        if deduction.se_ressemblent(voulu, titre_visible(cible.nom)):
            return cible

    # Vraiment en dernier : l ossature des consonnes. Un nom propre est ce
    # que la transcription deforme le plus, et deux mots faux sur deux font
    # echouer tout le reste -- « Rehman Muneeb » entendu « Rayman Monique ».
    for cible in cibles:
        if deduction.memes_consonnes(voulu, titre_visible(cible.nom)):
            return cible
    return None
