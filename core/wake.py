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

# Ce qui remet l assistant en veille avant la fin du compte a rebours.
#
# Ecrit sous forme NORMALISEE : sans accent, et l apostrophe devenue espace
# (« c'est bon » -> « c est bon »). Les deux langues, parce qu on ne pense
# pas a changer de langue pour dire « stop ».
MOTS_FIN_SESSION = {
    # Francais
    "stop", "stoppe", "arrete", "arrete toi", "arretez", "c est bon",
    "c est tout", "laisse tomber", "annule", "rien", "termine", "fini",
    "silence", "chut", "ca suffit", "suffit", "assez", "tais toi",
    "dors", "va dormir", "en veille", "mets toi en veille",
    "retourne en veille", "remets toi en veille", "repos",
    # Anglais
    "stop it", "that s all", "that s it", "that s enough", "enough",
    "never mind", "nevermind", "forget it", "cancel", "quiet", "be quiet",
    "shut up", "sleep", "go to sleep", "go back to sleep", "back to sleep",
    "stand by", "standby", "dismiss", "done", "nothing", "drop it",
}

# Mots qu on peut retirer d un ordre court sans en changer le sens :
# politesse, hesitations, interjections, marqueurs d accord.
#
# C est ce qui manquait le plus : « stop » tout seul etait reconnu, mais
# « ok stop », « stop s'il te plait », « bon stop merci » -- c est-a-dire ce
# qu on dit vraiment -- ne l etaient pas. Les articles et les possessifs
# n y figurent PAS : « arrete la musique » doit rester une commande, pas une
# mise en veille.
MOTS_EFFACABLES = {
    "euh", "heu", "hum", "hmm", "ben", "bah", "alors", "donc", "bon", "bien",
    "s", "il", "te", "vous", "plait", "stp", "please", "merci", "thanks",
    "thank", "you", "ok", "okay", "oui", "yes", "non", "no", "et", "puis",
    "maintenant", "now", "juste", "just",
}

# Ressemblance exigee quand l expression n est pas reconnue mot pour mot.
# « stope », « arretes », « sleeps » : la transcription d un mot isole est
# rarement parfaite, et c est justement le cas le plus frequent ici.
SEUIL_FIN_SESSION = 0.82
# En dessous, le flou attrape n importe quoi (« top » ressemble a « stop »
# a 86%). On exige alors le mot exact.
LONGUEUR_MINIMALE_FLOUE = 4

# Repliques de fin de session.
ACCUSES_FIN = ("Très bien.", "D'accord.", "Je me remets en veille.")
ACCUSES_FIN_EN = ("All right.", "Okay.", "Going back to sleep.")

# Etats renvoyes par l analyse.
IGNORE = "ignore"
REVEIL_SEUL = "reveil"
REVEIL_COMMANDE = "reveil_commande"
COMMANDE = "commande"
FIN_SESSION = "fin_session"


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


# Tolerance quand la phrase entiere se reduit au nom.
#
# Le seuil strict ci-dessus protege des conversations : dans « tu as vu Alba
# hier ? », un nom de quatre lettres attraperait n importe quoi. Mais une
# phrase d UN SEUL mot n est pas une conversation -- c est quelqu un qui
# appelle. Et c est precisement le cas ou la reconnaissance vocale se trompe
# le plus : sans contexte, elle n a rien pour trancher entre « Alma »,
# « Elma » et « Arma ». D ou un seuil de 0,75, qui rattrape exactement une
# lettre de travers sur un mot de quatre.
SEUIL_MOT_SEUL = 0.75


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
        self.tolere_seul = bool(lire("general.wake_tolerate_alone", True))
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
        # Comme pour le nom : si une tournure revient sans etre reconnue,
        # elle s ajoute dans voice.sleep_words, sans toucher au code.
        self.mots_fin = set(MOTS_FIN_SESSION)
        for extra in (lire("voice.sleep_words", ()) or ()):
            norme = " ".join(text_utils.tokenize(text_utils.normalize(str(extra))))
            if norme:
                self.mots_fin.add(norme)
        # Les memes, passes au meme filtre que la phrase entendue : « that s
        # all » se reduit a « that all », et « thanks that's all » aussi.
        self.mots_fin_reduits = {
            " ".join(self._reduire(text_utils.tokenize(mot))) for mot in self.mots_fin
        }
        self.mots_fin_reduits.discard("")
        self._arme_jusqu_a = 0.0

    # -- reconnaissance du nom ------------------------------------------------
    def est_mot_appel(self, mot: str, seul: bool = False) -> bool:
        """
        Le mot correspond-il au nom de l assistant ?

        `seul` indique que la phrase entiere se reduit a ce mot : on tolere
        alors l a-peu-pres, faute de quoi le simple fait d appeler par son
        nom -- sans rien d autre -- serait le cas le moins bien reconnu.
        """
        if not mot:
            return False
        if mot in self.variantes:
            return True
        seuil = self.seuil
        if seul and self.tolere_seul:
            seuil = min(seuil, SEUIL_MOT_SEUL)
        if seuil >= 1.0:
            return False        # nom court au milieu d une phrase : exact
        return text_utils.similarity(mot, self.mot_appel) >= seuil

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
        # « Alma » tout court : rien d autre a interpreter, donc rien a
        # confondre. Les prefixes techniques ne comptent pas comme un mot.
        utiles = [t for t in tokens if t not in self.prefixes]
        seul = len(utiles) <= 1

        index = None
        for position_mot in range(min(2, len(tokens))):
            if self.est_mot_appel(tokens[position_mot], seul=seul):
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

    def _reduire(self, tokens: list) -> list:
        """
        Ce qui reste d un ordre court : sans politesse, sans le nom, et sans
        les repetitions que produit la transcription (« stop stop »).
        """
        utiles = [t for t in tokens
                  if t not in MOTS_EFFACABLES and not self.est_mot_appel(t)]
        return [t for i, t in enumerate(utiles) if i == 0 or t != utiles[i - 1]]

    def est_fin_de_session(self, texte: str) -> bool:
        """
        La phrase demande-t-elle de remettre l assistant en veille ?

        Trois passes, de la plus stricte a la plus tolerante : la phrase
        telle quelle, puis ce qu il en reste une fois la politesse retiree
        (« stop » se dit rarement tout seul), puis la ressemblance, pour le
        mot isole que la transcription a ecorche.

        Ce qui reste doit valoir l expression ENTIERE : « arrete la musique »
        n est pas « arrete », et doit partir vers la commande.
        """
        tokens = text_utils.tokenize(text_utils.normalize(texte))
        brut = [t for i, t in enumerate(tokens) if i == 0 or t != tokens[i - 1]]
        if " ".join(brut) in self.mots_fin:
            return True

        utiles = self._reduire(tokens)
        if not utiles:
            return False
        norme = " ".join(utiles)
        if norme in self.mots_fin_reduits:
            return True

        # Un mot isole, mal transcrit : « stope », « arretes », « sleeps ».
        if len(utiles) > 1 or len(norme) < LONGUEUR_MINIMALE_FLOUE:
            return False
        return any(
            text_utils.similarity(norme, mot) >= SEUIL_FIN_SESSION
            for mot in self.mots_fin_reduits
            if " " not in mot and len(mot) >= LONGUEUR_MINIMALE_FLOUE
        )

    def analyser(self, texte: str) -> Analyse:
        """
        Decide quoi faire d une phrase entendue.

        La session d ecoute se PROLONGE apres chaque echange : une fois
        reveille, l assistant reste receptif et le compte a rebours repart a
        chaque phrase. Il ne se referme qu au silence, ou sur un « stop ».
        """
        texte = (texte or "").strip()
        if not texte:
            return Analyse(IGNORE)

        appel, reste = self.separer_mot_appel(texte)

        # La mise en veille se decide AVANT tout le reste. « Alma, stop » est
        # la facon la plus naturelle de le dire, et c est precisement celle
        # qui relancait une session au lieu de la fermer.
        #
        # Sans le nom, il faut qu une session soit ouverte : un « stop » lance
        # a quelqu un d autre dans la piece ne doit rien declencher.
        if (appel or self.arme) and self.est_fin_de_session(reste if appel else texte):
            self.desarmer()
            return Analyse(FIN_SESSION, "", appel)

        if appel and reste:
            self.armer()
            return Analyse(REVEIL_COMMANDE, reste, True)
        if appel:
            self.armer()
            return Analyse(REVEIL_SEUL, "", True)
        if self.arme:
            self.armer()           # on reparle : le compte a rebours repart
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


def accuse_fin(langue: str = "fr") -> str:
    """Replique quand la session se referme sur demande."""
    return random.choice(ACCUSES_FIN_EN if langue == "en" else ACCUSES_FIN)
