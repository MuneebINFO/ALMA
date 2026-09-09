"""
Chercher DANS un site, par sa propre barre de recherche.

Fabriquer une adresse de recherche -- « netflix.com/search?q=... » -- marche
sur les sites qui l acceptent, et sur eux seuls. Beaucoup n ont pas d adresse
de recherche stable, la changent, ou attendent d autres parametres : la page
s ouvre alors vide ou sur une erreur. Taper dans le champ du site, en
revanche, marche partout ou il y a un champ, et c est ce que fait un humain.

Encore faut-il le trouver. Trois cas, releves sur les sites reels :

    site          au repos                          apres la loupe
    LinkedIn      champ « Rechercher »              --
    YouTube       liste deroulante « Rechercher »   --
    Netflix       bouton « Search » seul            champ « Titles, people... »
    Prime Video   bouton « Rechercher dans... »     champ

D ou la marche a suivre : un champ nomme s il y en a un, sinon la LOUPE, dont
le nom parle toujours de recherche -- et le champ qui apparait derriere elle
ne se reconnait plus a son nom, mais au fait qu il vient d apparaitre.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

# Ce que les sites ecrivent autour de leur recherche, en francais comme en
# anglais. Sert a reconnaitre le champ, et surtout la loupe.
MOTS_RECHERCHE = ("recherche", "rechercher", "recherches", "search", "cherche",
                  "chercher", "buscar", "suche", "cerca")

TYPE_BOUTON = 50000
TYPE_LISTE = 50003          # ComboBox : YouTube, avec ses suggestions
TYPE_CHAMP = 50004          # Edit
TYPES_SAISIE = (TYPE_CHAMP, TYPE_LISTE)

# La loupe n est pas toujours un bouton : Disney+ en fait un LIEN, qui mene a
# une page de recherche au lieu de deplier un champ sur place.
TYPES_LOUPE = (TYPE_BOUTON, 50005, 50007, 50002)

LARGEUR_MIN = 80            # un champ de recherche n est jamais minuscule
PAUSE_APPARITION = 1.2      # le temps que le champ se deploie
DELAI_APRES_LOUPE = 7.0     # la loupe peut mener a une autre page
DELAI_PAGE = 9.0            # une page d accueil met plusieurs secondes a venir
PAUSE_SONDAGE = 0.5
PAUSE_FOCUS = 0.25
PAUSE_SAISIE = 0.2


def _est_une_recherche(nom: str) -> bool:
    """Le libelle parle-t-il de recherche ?"""
    from core import text_utils

    jetons = set(text_utils.tokenize(text_utils.normalize(nom or "")))
    return bool(jetons.intersection(MOTS_RECHERCHE))


def _parcourir(fenetre):
    """Les elements de la PAGE, avec leur type, leur nom et leur rectangle."""
    from core import browser_tabs, interaction

    uia, module = browser_tabs._client()
    if uia is None:
        return []
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        tous = racine.FindAll(module.TreeScope_Descendants, uia.CreateTrueCondition())
    except Exception as exc:
        log.debug("Page illisible : %s", exc)
        return []
    page = interaction.zone_page(fenetre)
    trouves = []
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            r = element.CurrentBoundingRectangle
            rect = (r.left, r.top, r.right, r.bottom)
            if rect[2] <= rect[0] or rect[3] <= rect[1]:
                continue
            if page is not None and not interaction._dans(rect, page):
                continue
            trouves.append((element, element.CurrentControlType,
                            (element.CurrentName or "").strip(), rect))
        except Exception:
            continue
    return trouves


def _cible(element, type_controle, nom, rect, fenetre):
    from core import interaction

    cible = interaction.Cible(nom, rect, element, type_controle)
    cible.fenetre = fenetre
    return cible


def champ_nomme(fenetre):
    """Un champ de saisie dont le libelle parle de recherche."""
    for element, type_controle, nom, rect in _parcourir(fenetre):
        if type_controle not in TYPES_SAISIE:
            continue
        if rect[2] - rect[0] < LARGEUR_MIN or not _est_une_recherche(nom):
            continue
        return _cible(element, type_controle, nom, rect, fenetre)
    return None


def n_importe_quel_champ(fenetre):
    """
    Le plus large champ de saisie de la page.

    Apres un clic sur la loupe, le champ qui se deploie ne porte pas toujours
    le mot « recherche » -- Netflix y met « Titles, people, genres ». C est
    alors le seul champ visible, et le plus grand.
    """
    candidats = [(element, type_controle, nom, rect)
                 for element, type_controle, nom, rect in _parcourir(fenetre)
                 if type_controle in TYPES_SAISIE and rect[2] - rect[0] >= LARGEUR_MIN]
    if not candidats:
        return None
    element, type_controle, nom, rect = max(
        candidats, key=lambda c: c[3][2] - c[3][0])
    return _cible(element, type_controle, nom, rect, fenetre)


def champ_unique(fenetre):
    """
    L unique champ de saisie de la page, s il n y en a qu un.

    La recherche d un site reste parfois ouverte d une fois sur l autre : le
    champ est la, mais la loupe a disparu et le libelle ne dit plus rien de
    la recherche. Tant qu il n y a qu un seul champ, l ambiguite n existe
    pas -- des qu il y en a plusieurs, on prefere ne rien supposer.
    """
    champs = [(element, type_controle, nom, rect)
              for element, type_controle, nom, rect in _parcourir(fenetre)
              if type_controle in TYPES_SAISIE and rect[2] - rect[0] >= LARGEUR_MIN]
    if len(champs) != 1:
        return None
    return _cible(*champs[0], fenetre)


def bouton_loupe(fenetre):
    """
    Ce qui ouvre la recherche, quand le champ n est pas deja la.

    Bouton le plus souvent, mais Disney+ en fait un lien : on accepte donc
    tout ce qui se clique, du moment que le libelle parle de recherche.
    """
    for element, type_controle, nom, rect in _parcourir(fenetre):
        if type_controle in TYPES_LOUPE and _est_une_recherche(nom):
            return _cible(element, type_controle, nom, rect, fenetre)
    return None


def trouver_le_champ(fenetre, deplier: bool = True, delai: float = DELAI_PAGE):
    """
    Le champ de recherche du site, en depliant la loupe s il le faut.

    On patiente : une page d accueil de service de streaming met plusieurs
    secondes a se construire, et sa barre de recherche arrive avec le reste.
    Mesure sur Prime Video : rien apres trois secondes et demie, la loupe
    apres cinq.

    Retourne une cible, ou None si la page n en propose aucune.
    """
    from core import interaction

    fin = time.time() + max(0.0, delai)
    loupe = None
    while True:
        champ = champ_nomme(fenetre)
        if champ is not None:
            return champ
        if deplier:
            loupe = bouton_loupe(fenetre)
            if loupe is not None:
                break
        if time.time() >= fin:
            break
        time.sleep(PAUSE_SONDAGE)

    if not deplier:
        return None
    if loupe is not None:
        return _deplier(fenetre, loupe)
    # Pas de loupe : la recherche est peut-etre deja ouverte.
    return champ_unique(fenetre)


def _deplier(fenetre, loupe):
    """
    Clique la loupe, et verifie qu un champ apparait vraiment.

    L activation par l API d accessibilite repond « c est fait » sans que
    rien ne bouge sur certains sites -- mesure sur Prime Video, ou seul un
    vrai clic de souris deplie la recherche. On regarde donc le resultat
    plutot que la reponse, et on insiste a la souris si besoin.
    """
    from core import interaction

    for physique in (False, True):
        if not interaction.cliquer(loupe, physique=physique):
            continue
        # La loupe deplie parfois un champ sur place, parfois elle CHANGE DE
        # PAGE -- Disney+ mene a une page de recherche. On sonde donc au lieu
        # d attendre une duree fixe.
        fin = time.time() + DELAI_APRES_LOUPE
        while True:
            champ = champ_nomme(fenetre) or n_importe_quel_champ(fenetre)
            if champ is not None:
                return champ
            if time.time() >= fin:
                break
            time.sleep(PAUSE_SONDAGE)
    return None


def saisir(fenetre, champ, requete: str) -> bool:
    """
    Ecrit la requete dans le champ et valide.

    On donne le focus par l API d accessibilite, puis on tape : ecrire la
    valeur directement serait ignore par la plupart des pages, qui n ecoutent
    que les evenements du clavier.
    """
    from core import desktop, win_utils

    try:
        import ctypes

        actif = ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        actif = 0
    if actif != fenetre.handle and not desktop.mettre_au_premier_plan(fenetre.handle):
        return False
    try:
        champ.element.SetFocus()
    except Exception as exc:
        log.debug("Focus du champ impossible : %s", exc)
        from core import interaction

        if not interaction.cliquer(champ, physique=True):
            return False
    time.sleep(PAUSE_FOCUS)
    # Le champ peut contenir une recherche precedente.
    win_utils.press_combo(win_utils.VK_CONTROL, ord("A"))
    time.sleep(0.1)
    if not win_utils.type_text(requete):
        return False
    time.sleep(PAUSE_SAISIE)
    return win_utils.press_key(win_utils.VK_RETURN)


def chercher(fenetre, requete: str) -> bool:
    """Cherche `requete` dans le site affiche. False si la page ne s y prete pas."""
    if not (requete or "").strip():
        return False
    champ = trouver_le_champ(fenetre)
    if champ is None:
        return False
    return saisir(fenetre, champ, requete.strip())
