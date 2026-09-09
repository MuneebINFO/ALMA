"""
Poser la question a l IA de Google, par le navigateur, en arriere-plan.

Aucune API, aucune cle, aucun compte a configurer : la reponse de Gemini est
deja sur google.com, en tete des resultats, sous le titre « Apercu IA ». Alma
ouvre donc une recherche dans une fenetre qu elle REDUIT aussitot, lit la
reponse par l API d accessibilite -- comme elle lit deja n importe quelle page
-- puis referme la fenetre. Rien ne reste a l ecran, et la reponse est dite
comme si Alma repondait elle-meme.

Trois mesures fondent ce fonctionnement, et expliquent pourquoi il tient :

  - une fenetre Chrome qui n est PAS au premier plan reste lisible : 1048
    elements mesures sur une fenetre d arriere-plan ;
  - une fenetre REDUITE l est tout autant : 226 elements, ancre comprise, que
    la fenetre soit visible, reduite ou restauree ;
  - en revanche, une page qui vient d etre chargee n expose rien pendant une
    seconde ou deux : Chromium construit son arbre a retardement. D ou
    l attente active plutot qu une lecture unique.

Dans la page, l « Apercu IA » annonce le bloc, et la reponse est la premiere
phrase qui le suit.
"""

from __future__ import annotations

import ctypes
import logging
import os
import subprocess
import time
from urllib.parse import quote_plus

log = logging.getLogger(__name__)

RECHERCHE = "https://www.google.com/search?hl=fr&q="

# L element qui annonce la reponse de l IA dans la page.
ANCRES = ("apercu ia", "aperçu ia", "ai overview")

TYPE_DOCUMENT = 50030

# En deca, une ligne qui ne se termine pas est un libelle d interface, pas une
# phrase.
LONGUEUR_PROSE = 40

# U+FFFC remplace les images dans le texte rendu par l accessibilite.
OBJET_INCORPORE = "￼"

SW_MINIMISER = 6
WM_CLOSE = 0x0010

# La page met une a deux secondes a exposer son contenu, et l apercu IA arrive
# apres le reste : il s ecrit progressivement.
DELAI_PAGE = 20.0
PAUSE_SONDAGE = 0.6
# Une fois l ancre trouvee, on laisse la reponse finir de s ecrire.
STABILITE_REQUISE = 1.2

# La reponse est LUE a voix haute : au-dela, on coupe proprement.
LONGUEUR_MAX = 600

ABSENCE_DE_NAVIGATEUR = (
    "Je ne trouve pas Chrome sur cette machine. Renseignez son chemin dans "
    "applications.chrome.paths, dans config.yaml."
)


class GeminiProvider:
    """Provider qui lit l apercu IA de Google, sans rien montrer a l ecran."""

    name = "gemini"

    def __init__(self, config) -> None:
        self.config = config
        lire = config.get if config else (lambda cle, defaut=None: defaut)
        self.delai = float(lire("ai_fallback.gemini.timeout_seconds", DELAI_PAGE)
                           or DELAI_PAGE)

    # -- verifications prealables --------------------------------------------
    def navigateur(self) -> str:
        """Chemin du navigateur, ou chaine vide."""
        entree = (self.config.get("applications.chrome.paths", []) if self.config else [])
        for candidat in list(entree) + ["chrome.exe"]:
            chemin = os.path.expandvars(str(candidat))
            if os.path.isfile(chemin):
                return chemin
        import shutil

        return shutil.which("chrome.exe") or ""

    def diagnostic(self) -> str:
        """Ce qui empeche de fonctionner, ou une chaine vide si tout est pret."""
        return "" if self.navigateur() else ABSENCE_DE_NAVIGATEUR

    # -- appel ---------------------------------------------------------------
    def generate(self, query: str) -> str:
        """Pose la question a Google et rend l apercu IA. Ne leve jamais."""
        query = (query or "").strip()
        if not query:
            return "Je n'ai pas saisi la question."
        souci = self.diagnostic()
        if souci:
            return souci

        fenetre = None
        try:
            fenetre = _ouvrir_discretement(self.navigateur(),
                                           RECHERCHE + quote_plus(query))
            if fenetre is None:
                return "Je n'ai pas réussi à ouvrir la recherche."
            reponse = _attendre_l_apercu(fenetre, self.delai)
        except Exception as exc:
            log.debug("Lecture de l apercu Google impossible : %s", exc)
            reponse = ""
        finally:
            if fenetre is not None:
                _fermer(fenetre)

        if not reponse:
            return ("Je n'ai pas trouvé de réponse à cette question.")
        return _raccourcir(reponse)


# --------------------------------------------------------------------------
# La fenetre : ouverte, reduite aussitot, refermee ensuite
# --------------------------------------------------------------------------
def _ouvrir_discretement(binaire: str, url: str):
    """
    Ouvre la recherche dans une fenetre qui ne reste pas a l ecran.

    Chrome prend le premier plan en s ouvrant, on ne peut pas l en empecher.
    On le lui reprend donc des que la fenetre existe : elle est reduite, et le
    focus rendu a ce qui l avait. Ce qui se voit se compte en fractions de
    seconde, et rien ne demeure.
    """
    from core import desktop

    user32 = ctypes.windll.user32
    connues = {f.handle for f in desktop.fenetres()}
    devant = user32.GetForegroundWindow()

    subprocess.Popen(
        [binaire, "--new-window", url],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    fin = time.time() + 15.0
    while time.time() < fin:
        time.sleep(0.2)
        for fenetre in desktop.fenetres():
            if fenetre.handle in connues or not fenetre.est_navigateur:
                continue
            user32.ShowWindow(fenetre.handle, SW_MINIMISER)
            if devant:
                desktop.mettre_au_premier_plan(devant)
            return fenetre
    return None


def _fermer(fenetre) -> None:
    """Referme la fenetre de travail, quoi qu il soit arrive."""
    try:
        ctypes.windll.user32.PostMessageW(fenetre.handle, WM_CLOSE, 0, 0)
    except Exception as exc:
        log.debug("Fermeture de la fenetre de recherche impossible : %s", exc)


# --------------------------------------------------------------------------
# La lecture
# --------------------------------------------------------------------------
def _texte_de_la_page(fenetre) -> str:
    """
    Le texte de la page, dans l ORDRE DE LECTURE.

    On lit le document entier plutot que d assembler les elements un a un.
    Recoller des fragments par leurs coordonnees paraissait plus fin ; c etait
    plus fragile : un mot qui est un lien forme un element a part, et quand la
    phrase passe a la ligne il se retrouvait a la fin, ou perdu. « Le roman Les
    Miserables a ete ecrit par » sans Victor Hugo. Le document, lui, rend le
    texte tel qu il se lit, liens compris.
    """
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if uia is None:
        return ""
    try:
        racine = uia.ElementFromHandle(fenetre.handle)
        tous = racine.FindAll(module.TreeScope_Descendants, uia.CreateTrueCondition())
    except Exception as exc:
        log.debug("Arbre de la page illisible : %s", exc)
        return ""

    meilleur = ""
    for index in range(tous.Length):
        try:
            element = tous.GetElement(index)
            if element.CurrentControlType != TYPE_DOCUMENT:
                continue
            motif = element.GetCurrentPattern(module.UIA_TextPatternId)
            if not motif:
                continue
            texte = motif.QueryInterface(module.IUIAutomationTextPattern)                          .DocumentRange.GetText(-1)
        except Exception:
            continue
        if texte and len(texte) > len(meilleur):
            meilleur = texte
    return meilleur


def _est_de_la_prose(ligne: str) -> bool:
    """
    Cette ligne est-elle une phrase, ou un bout d interface ?

    Autour de la reponse vivent des libelles -- « A propos de ce resultat »,
    le nom d un site, une puce -- et des caracteres de remplacement la ou se
    trouvent les images. Une phrase, elle, est longue ou se termine.
    """
    ligne = ligne.strip()
    if not ligne or ligne.startswith("•"):
        return False
    if ligne.endswith(("Résultats associés", "S'ouvre dans un nouvel onglet.")):
        return False
    return len(ligne) >= LONGUEUR_PROSE or ligne.endswith((".", "!", "?"))


def apercu(fenetre) -> str:
    """
    La reponse de l IA telle qu elle est affichee, ou une chaine vide.

    L « Apercu IA » annonce le bloc ; la reponse est la premiere phrase qui le
    suit. Ce qui vient ensuite est un complement -- une fiche, des puces, des
    sources : ecrit, cela se parcourt ; dit, cela se subit.
    """
    texte = _texte_de_la_page(fenetre).replace(OBJET_INCORPORE, " ")
    bas = texte.lower()
    depart = -1
    for ancre in ANCRES:
        depart = bas.find(ancre)
        if depart >= 0:
            depart += len(ancre)
            break
    if depart < 0:
        return ""

    for ligne in texte[depart:].splitlines():
        if _est_de_la_prose(ligne):
            return " ".join(ligne.split())
    return ""


def _attendre_l_apercu(fenetre, delai: float) -> str:
    """
    Attend que l apercu apparaisse, puis qu il cesse de s ecrire.

    Deux attentes en une : la page met une a deux secondes a exposer quoi que
    ce soit, et l apercu s ecrit ensuite progressivement. On rend ce qu on a
    des qu il ne grandit plus.
    """
    fin = time.time() + max(1.0, delai)
    dernier, stable_depuis = "", None
    while time.time() < fin:
        time.sleep(PAUSE_SONDAGE)
        courant = apercu(fenetre)
        if not courant:
            continue
        if courant == dernier:
            if stable_depuis is None:
                stable_depuis = time.time()
            elif time.time() - stable_depuis >= STABILITE_REQUISE:
                return courant
        else:
            dernier, stable_depuis = courant, None
    return dernier


def _raccourcir(texte: str) -> str:
    """Ramene la reponse a ce qui s ecoute, en coupant a une fin de phrase."""
    texte = " ".join((texte or "").split())
    if len(texte) <= LONGUEUR_MAX:
        return texte
    coupe = texte[:LONGUEUR_MAX]
    for ponctuation in (". ", "! ", "? "):
        position = coupe.rfind(ponctuation)
        if position > LONGUEUR_MAX // 2:
            return coupe[:position + 1].strip()
    return coupe.rsplit(" ", 1)[0].strip() + "…"
