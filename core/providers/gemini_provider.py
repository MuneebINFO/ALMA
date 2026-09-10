"""
Poser la question au MODE IA de Google, par le navigateur, en arriere-plan.

Aucune API, aucune cle, aucun compte a configurer. Alma ouvre la recherche
dans une fenetre qu elle REDUIT aussitot, lit la reponse par l API
d accessibilite -- comme elle lit deja n importe quelle page -- puis referme
la fenetre. Rien ne reste a l ecran, et la reponse est dite comme si Alma
repondait elle-meme.

Pourquoi le mode IA et non gemini.google.com, qui serait plus direct : parce
que celui-la ne repond QUE devant vous. Mesure faite sur la meme question --
fenetre reduite, la reponse n arrive jamais ; fenetre visible mais derriere,
non plus ; fenetre au premier plan, dix secondes. Chrome met en veille le
rendu des fenetres masquees, et l application cesse d ecrire. Le mode IA, lui,
est une page de resultats : elle se rend meme reduite.

Trois mesures fondent ce fonctionnement, et expliquent pourquoi il tient :

  - une fenetre Chrome qui n est PAS au premier plan reste lisible : 1048
    elements mesures sur une fenetre d arriere-plan ;
  - une fenetre REDUITE l est tout autant : 226 elements, que la fenetre soit
    visible, reduite ou restauree ;
  - en revanche, une page qui vient d etre chargee n expose rien pendant une
    seconde ou deux : Chromium construit son arbre a retardement. D ou
    l attente active plutot qu une lecture unique.

Dans la page, la question est rappelee avant la reponse : c est elle qui sert
de repere, et la reponse est la premiere phrase qui la suit.
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
import subprocess
import time
from urllib.parse import quote_plus

log = logging.getLogger(__name__)

# udm=50 : le MODE IA de Google. C est une page de resultats, pas une
# application, et c est ce qui change tout -- gemini.google.com cesse
# d ecrire sa reponse des que sa fenetre n est plus au premier plan ;
# celle-ci se rend meme reduite.
RECHERCHE = "https://www.google.com/search?udm=50&hl=fr&q="

# Consigne ajoutee a CHAQUE question. Le mode IA repond volontiers par un
# dossier -- paragraphes, listes, sources -- dont Alma ne lit que le premier
# fragment, et pas toujours le bon. Une reponse courte et directe est plus
# sure a extraire et plus supportable a l oreille. Elle est glissee entre
# parentheses, sur la meme ligne que la question, pour rester un simple
# complement et non une deuxieme demande.
CONSIGNE = "réponds en une ou deux phrases, sans détour"


def _avec_consigne(question: str) -> str:
    """La question, suivie de la consigne de concision -- sauf si l utilisateur
    a deja demande quelque chose de ce genre."""
    question = (question or "").strip()
    if "phrase" in question.lower() or "bref" in question.lower():
        return question
    return question + " (" + CONSIGNE + ")"

TYPE_DOCUMENT = 50030

# En deca, une ligne qui ne se termine pas est un libelle d interface, pas une
# phrase.
LONGUEUR_PROSE = 40

# Ce qui, sous la reponse, n en fait plus partie. L avertissement de bas de
# page est une phrase complete : sans l ecarter, il passe pour la reponse des
# que la vraie est trop courte pour en avoir l air.
FINS_DE_REPONSE = (
    "Les réponses de l'IA peuvent contenir des erreurs",
    "Résultats de recherche",
    "Historique du Mode",
)

# Un debut de reponse chiffree : « 15 x 4 = », « 60 ». Ni l un ni l autre ne
# ressemble a une phrase, et pourtant les deux le sont ensemble.
DEBUT_CHIFFRE = re.compile(r"^[\d\s.,+\-*/=x×%()€$]+$")

# U+FFFC remplace les images dans le texte rendu par l accessibilite.
OBJET_INCORPORE = "￼"

SW_MINIMISER = 6
WM_CLOSE = 0x0010

# La page met une a deux secondes a exposer son contenu, et la reponse arrive
# apres le reste : elle s ecrit progressivement.
DELAI_PAGE = 20.0
PAUSE_SONDAGE = 0.6
# Une fois la reponse reperee, on la laisse finir de s ecrire.
STABILITE_REQUISE = 1.2

# La reponse est LUE a voix haute : au-dela, on coupe proprement.
LONGUEUR_MAX = 600

ABSENCE_DE_NAVIGATEUR = (
    "Je ne trouve pas Chrome sur cette machine. Renseignez son chemin dans "
    "applications.chrome.paths, dans config.yaml."
)


class GeminiProvider:
    """Provider qui lit le mode IA de Google, sans rien montrer a l ecran."""

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
        """Pose la question au mode IA et rend sa reponse. Ne leve jamais."""
        query = (query or "").strip()
        if not query:
            return "Je n'ai pas saisi la question."
        souci = self.diagnostic()
        if souci:
            return souci

        fenetre = None
        try:
            fenetre = _ouvrir_discretement(self.navigateur(),
                                           RECHERCHE + quote_plus(_avec_consigne(query)))
            if fenetre is None:
                return "Je n'ai pas réussi à ouvrir la recherche."
            trouvee = _attendre_la_reponse(fenetre, query, self.delai)
        except Exception as exc:
            log.debug("Lecture du mode IA impossible : %s", exc)
            trouvee = ""
        finally:
            if fenetre is not None:
                _fermer(fenetre)

        if not trouvee:
            return "Je n'ai pas trouvé de réponse à cette question."
        return _raccourcir(trouvee)


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
    if any(marque in ligne for marque in FINS_DE_REPONSE):
        return False
    return len(ligne) >= LONGUEUR_PROSE or ligne.endswith((".", "!", "?"))


def _sans_blancs(texte: str) -> str:
    return " ".join((texte or "").split()).lower()


def _est_un_debut_de_reponse(ligne: str) -> bool:
    """
    Une ligne courte peut ouvrir la reponse au lieu d etre du decor.

    C est le cas des calculs, que Google decoupe : « 15 x 4 = » d un cote,
    « 60 » de l autre. On n accepte que ce qui ne contient que des chiffres et
    des signes -- un libelle d interface, lui, contient des mots.
    """
    return bool(DEBUT_CHIFFRE.match(ligne))


def reponse(fenetre, question: str) -> str:
    """
    La reponse du mode IA, ou une chaine vide tant qu elle n est pas la.

    La page rappelle la QUESTION, puis y repond : c est donc la question qui
    sert de repere. S accrocher a un titre de section -- « Apercu IA » --
    marcherait en francais et nulle part ailleurs ; la question, elle, est
    celle qu on vient d envoyer.

    On ne garde que la premiere phrase. Ce qui suit est un complement : des
    puces, des sources, une proposition de suite. Ecrit, cela se parcourt ;
    dit, cela se subit.
    """
    texte = _texte_de_la_page(fenetre).replace(OBJET_INCORPORE, " ")
    if not texte:
        return ""

    lignes = texte.splitlines()
    cherchee = _sans_blancs(question)
    depart = None
    for index, ligne in enumerate(lignes):
        nette = _sans_blancs(ligne)
        # La question est rappelee telle qu elle a ete envoyee -- la consigne
        # de concision ajoutee entre parentheses comprise. On accroche donc
        # sur son DEBUT, pas sur une egalite stricte. Et la PREMIERE
        # occurrence seule : plus bas, la question est un titre de resultat
        # (« pourquoi le ciel est bleu » y est aussi une video, dont le
        # descriptif revenait a la place de la reponse).
        if nette == cherchee or nette.startswith(cherchee + " "):
            depart = index + 1
            break
    if depart is None:
        return ""

    echo = _sans_blancs(_avec_consigne(question))
    morceaux = []
    for ligne in lignes[depart:]:
        nette = " ".join(ligne.split())
        if not nette:
            continue
        if _sans_blancs(nette) and _sans_blancs(nette) in echo:
            # Reste de la question ou de la consigne, encore en echo sur
            # plusieurs lignes : ce n est pas la reponse.
            continue
        if any(marque in nette for marque in FINS_DE_REPONSE):
            break
        if not _est_de_la_prose(nette):
            # Une reponse peut tenir en deux bouts trop courts pour etre pris
            # separement pour des phrases : « 15 x 4 = », puis « 60 ». Les
            # sauter laissait passer l avertissement de bas de page, qui lui
            # est bien une phrase -- et Alma lisait « les reponses de l IA
            # peuvent contenir des erreurs ».
            if morceaux or _est_un_debut_de_reponse(nette):
                morceaux.append(nette)
                continue
            break
        morceaux.append(nette)
        break
    return _raccourcir(" ".join(morceaux))


def _attendre_la_reponse(fenetre, question: str, delai: float) -> str:
    """
    Attend que la reponse apparaisse, puis qu elle cesse de s ecrire.

    Deux attentes en une : la page met une a deux secondes a exposer quoi que
    ce soit, et la reponse s ecrit ensuite progressivement. On rend ce qu on a
    des qu elle ne grandit plus.
    """
    fin = time.time() + max(1.0, delai)
    dernier, stable_depuis = "", None
    while time.time() < fin:
        time.sleep(PAUSE_SONDAGE)
        courant = reponse(fenetre, question)
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
