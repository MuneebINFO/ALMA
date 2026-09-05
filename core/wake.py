"""
Detection du mot d appel et machine a etats de l ecoute.

L assistant ecoute en permanence mais reste passif : il n agit que si la
phrase commence par son nom, ou s il vient d etre reveille.

Trois situations :
  - « Alma, quelle heure est-il »  -> commande executee directement
  - « Alma » suivi d un blanc      -> accuse de reception, puis l assistant
                                      reste arme quelques secondes et la
                                      phrase suivante est traitee comme une
                                      commande
  - toute autre phrase             -> ignoree (conversation ambiante)

Le mot d appel vient ENTIEREMENT de la configuration : changer de nom ne
demande de toucher a aucun fichier de code.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from core import text_utils

# Mots sans contenu : « Alma euh... » equivaut a « Alma » tout court.
REMPLISSAGE = {"euh", "heu", "hum", "hmm", "ben", "bah", "alors", "donc",
               "s il te plait", "stp", "please"}

# Prefixes d appel toleres avant le nom.
PREFIXES_PAR_DEFAUT = ("ok", "hey", "he", "eh", "dis")

# Repliques quand on appelle l assistant sans rien demander.
ACCUSES = (
    "Oui ?",
    "Je vous écoute.",
    "Oui, je suis là.",
    "À votre service.",
)

# Etats renvoyes par l analyse.
IGNORE = "ignore"
REVEIL_SEUL = "reveil"
REVEIL_COMMANDE = "reveil_commande"
COMMANDE = "commande"


@dataclass
class Analyse:
    """Resultat de l analyse d une phrase entendue."""

    etat: str
    commande: str = ""
    mot_appel_detecte: bool = False


def accuse_reception() -> str:
    """Replique courte, comme le ferait un assistant qu on interpelle."""
    return random.choice(ACCUSES)


def seuil_similarite(mot: str) -> float:
    """
    Tolerance aux erreurs de transcription, ADAPTEE A LA LONGUEUR DU MOT.

    Un nom court partage mecaniquement beaucoup de lettres avec des mots
    frequents : « alma » et « alba » se ressemblent a 75%. Appliquer le meme
    seuil a tous les noms ferait donc reveiller l assistant sans arret. On
    exige donc une correspondance exacte en dessous de cinq lettres, et on
    ne tolere du flou que sur les noms assez longs pour le supporter.
    """
    longueur = len(mot)
    if longueur <= 4:
        return 1.0
    if longueur == 5:
        return 0.85
    if longueur == 6:
        return 0.80
    return 0.75


def generer_variantes(mot: str) -> set:
    """
    Variantes d orthographe que la reconnaissance vocale peut produire.

    Regles volontairement prudentes (finales muettes, h initial, confusions
    de lettres courantes en francais). Elles ne couvrent pas tout : si vous
    constatez une transcription recurrente non reconnue, ajoutez-la dans
    general.wake_variants.
    """
    mot = text_utils.normalize(mot).strip()
    if not mot:
        return set()
    variantes = {mot}
    # Finales muettes ajoutees par la transcription.
    variantes.update(mot + suffixe for suffixe in ("t", "s", "e", "a", "h"))
    # H initial (non prononce en francais).
    variantes.add("h" + mot)
    # Confusions de lettres frequentes.
    for depuis, vers in (("c", "k"), ("k", "c"), ("s", "z"), ("z", "s"),
                         ("i", "y"), ("y", "i"), ("f", "ph")):
        if depuis in mot:
            variantes.add(mot.replace(depuis, vers))
    return {v for v in variantes if v}


class MoteurEcoute:
    """
    Machine a etats : passif -> arme -> passif.

    Une fois reveille, l assistant reste receptif pendant `duree_armement`
    secondes pour qu on puisse enchainer la commande sans repeter son nom.

    Tout vient de la configuration : le nom, ses variantes, les prefixes
    tolerees, et le fait qu un prefixe soit obligatoire ou non.
    """

    def __init__(self, config=None, duree_armement: float | None = None) -> None:
        self.config = config
        lire = config.get if config is not None else (lambda cle, defaut=None: defaut)

        self.mot_appel = text_utils.normalize(
            str(lire("general.wake_word", "alma") or "alma")
        ).strip()
        self.prefixes = tuple(
            text_utils.normalize(str(p)).strip()
            for p in (lire("general.wake_prefixes", PREFIXES_PAR_DEFAUT) or ())
        )
        self.prefixe_obligatoire = bool(lire("general.wake_require_prefix", False))
        self.duree_armement = float(
            duree_armement if duree_armement is not None
            else lire("voice.armed_seconds", 12)
        )

        self.variantes = generer_variantes(self.mot_appel)
        for extra in (lire("general.wake_variants", ()) or ()):
            norme = text_utils.normalize(str(extra)).strip()
            if norme:
                self.variantes.add(norme)
        self.seuil = seuil_similarite(self.mot_appel)
        self._arme_jusqu_a = 0.0

    # -- reconnaissance du nom ------------------------------------------------
    def est_mot_appel(self, mot: str) -> bool:
        """Le mot correspond-il au nom de l assistant ?"""
        if not mot:
            return False
        if mot in self.variantes:
            return True
        if self.seuil >= 1.0:
            return False        # nom court : correspondance exacte exigee
        return text_utils.similarity(mot, self.mot_appel) >= self.seuil

    def separer_mot_appel(self, texte: str) -> tuple[bool, str]:
        """
        Retire le mot d appel en tete de phrase.
        Retourne (mot_appel_present, reste_de_la_phrase).
        """
        norm = text_utils.normalize(texte)
        tokens = text_utils.tokenize(norm)
        if not tokens:
            return False, ""

        # Le nom est cherche dans les deux premiers mots : cela couvre
        # « Alma ... », « OK Alma ... » et aussi « Salut Alma ».
        index = None
        for position_mot in range(min(2, len(tokens))):
            if self.est_mot_appel(tokens[position_mot]):
                index = position_mot
                break
        if index is None:
            return False, texte.strip()
        if self.prefixe_obligatoire and index == 0:
            return False, texte.strip()

        # Ce qui precede le nom : les prefixes techniques (« ok ») sont jetes,
        # le reste est conserve -- « Salut Alma » doit rester une salutation.
        avant = [t for t in tokens[:index] if t not in self.prefixes]
        apres = tokens[index + 1:]
        while apres and apres[0] in REMPLISSAGE:
            apres.pop(0)

        if not apres:
            return True, " ".join(avant)
        # On repart du texte d origine pour garder accents et casse.
        debut_apres = norm.find(apres[0], _fin_du_mot(norm, tokens, index))
        suite = texte[debut_apres:].strip() if debut_apres >= 0 else " ".join(apres)
        return True, ((" ".join(avant) + " " + suite).strip() if avant else suite)

    # -- machine a etats ------------------------------------------------------
    @property
    def arme(self) -> bool:
        return time.monotonic() < self._arme_jusqu_a

    def armer(self) -> None:
        self._arme_jusqu_a = time.monotonic() + self.duree_armement

    def desarmer(self) -> None:
        self._arme_jusqu_a = 0.0

    def secondes_restantes(self) -> float:
        return max(0.0, self._arme_jusqu_a - time.monotonic())

    def analyser(self, texte: str) -> Analyse:
        """Decide quoi faire d une phrase entendue."""
        texte = (texte or "").strip()
        if not texte:
            return Analyse(IGNORE)

        appel, reste = self.separer_mot_appel(texte)

        if appel and reste:
            self.desarmer()
            return Analyse(REVEIL_COMMANDE, reste, True)
        if appel:
            self.armer()
            return Analyse(REVEIL_SEUL, "", True)
        if self.arme:
            self.desarmer()
            return Analyse(COMMANDE, texte, False)
        return Analyse(IGNORE, texte, False)


def _fin_du_mot(norm: str, tokens: list, index: int) -> int:
    """Position, dans la chaine normalisee, juste apres le token demande."""
    curseur = 0
    for i, token in enumerate(tokens):
        curseur = norm.find(token, curseur)
        if curseur < 0:
            return 0
        curseur += len(token)
        if i == index:
            return curseur
    return curseur
