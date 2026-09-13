"""
Le premier lancement : quatre questions, une fois.

A l installation, Alma ne sait rien de vous -- pas votre nom, pas votre
langue, pas la voix que vous voulez entendre. Plutot que de choisir a votre
place et d esperer que vous trouviez ou changer, il demande.

QUATRE questions, pas douze : un assistant qui ouvre un formulaire avant de
servir a quoi que ce soit se fait fermer. Tout le reste garde sa valeur par
defaut, et se change ensuite d une phrase -- c est bien l interet d avoir
mis la personnalisation a la voix (voir commands/preferences.py).

La LANGUE vient en premier, et c est voulu : les trois questions suivantes
se posent alors dans la langue choisie.

Ce module ne connait ni Tkinter ni le terminal. Il decrit les questions et
traduit les reponses en reglages ; l interface graphique (gui.py) et le mode
texte (main.py) les posent chacun a leur facon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core import preferences as prefs

# Le reglage qui dit que c est fait. Sans lui, la question reviendrait a
# chaque lancement -- et « passer » ne servirait a rien.
CLE_TERMINE = "general.setup_done"


@dataclass(frozen=True)
class Choix:
    """Une reponse possible a une question fermee."""

    valeur: str
    libelle_fr: str
    libelle_en: str

    def libelle(self, langue: str) -> str:
        return self.libelle_en if langue == "en" else self.libelle_fr


@dataclass(frozen=True)
class Question:
    """
    Une question du premier lancement.

    Sans `choix`, c est un champ libre. `defaut` est ce qu on garde quand la
    reponse est vide : on n insiste jamais, une question sautee laisse la
    valeur par defaut en place.
    """

    cle: str
    titre_fr: str
    titre_en: str
    aide_fr: str = ""
    aide_en: str = ""
    choix: tuple = field(default_factory=tuple)
    defaut: str = ""

    def titre(self, langue: str) -> str:
        return self.titre_en if langue == "en" else self.titre_fr

    def aide(self, langue: str) -> str:
        return self.aide_en if langue == "en" else self.aide_fr

    @property
    def libre(self) -> bool:
        return not self.choix


QUESTIONS = (
    Question(
        cle="langue",
        # Cette question-la seule se pose dans les deux langues a la fois :
        # on ne sait pas encore laquelle parler.
        titre_fr="Quelle langue parlez-vous ?",
        titre_en="Quelle langue parlez-vous ? / What language do you speak?",
        aide_fr="Je vous répondrai dans cette langue. Vous pourrez m'en changer "
                "à tout moment.",
        aide_en="Je vous répondrai dans cette langue / I'll answer you in that "
                "language.",
        choix=(
            Choix("fr", "Français", "Français"),
            Choix("en", "English", "English"),
        ),
        defaut="fr",
    ),
    Question(
        cle="nom_utilisateur",
        titre_fr="Comment dois-je vous appeler ?",
        titre_en="What should I call you?",
        aide_fr="Votre prénom, pour vous saluer. Laissez vide si vous préférez.",
        aide_en="Your first name, so I can greet you. Leave it empty if you'd rather.",
    ),
    Question(
        cle="nom_assistant",
        titre_fr="Et moi, comment voulez-vous m'appeler ?",
        titre_en="And me — what would you like to call me?",
        aide_fr="C'est le nom que vous direz pour me réveiller. Trois lettres "
                "au minimum.",
        aide_en="This is the name you'll say to wake me. Three letters minimum.",
        defaut="ALMA",
    ),
    Question(
        cle="voix",
        titre_fr="Quelle voix préférez-vous ?",
        titre_en="Which voice do you prefer?",
        aide_fr="Vous pourrez en changer, comme tout le reste.",
        aide_en="You can change it later, like everything else.",
        choix=(
            Choix("femme", "Une voix de femme", "A female voice"),
            Choix("homme", "Une voix d'homme", "A male voice"),
        ),
        defaut="femme",
    ),
)

PAR_CLE = {question.cle: question for question in QUESTIONS}


def est_necessaire(config) -> bool:
    """Le premier lancement a-t-il encore lieu ?"""
    return not bool(config.get(CLE_TERMINE, False))


def reglages_pour(cle: str, reponse: str, config) -> dict:
    """
    Traduit une reponse en reglages de configuration.

    Retourne un dictionnaire vide quand il n y a rien a retenir : une
    reponse vide, ou la valeur qui etait deja en place. Le nom de
    l assistant depend de la langue deja choisie -- d ou le `config`.

    On n ecrit QUE ce qui change. Sans cela, valider le nom pre-rempli ou
    passer la question de la voix inscrivait la valeur par defaut dans les
    preferences : elle apparaissait ensuite dans « mes preferences » comme
    un choix, alors que personne n avait rien choisi.
    """
    return {chemin: valeur
            for chemin, valeur in _reglages_bruts(cle, reponse, config).items()
            if valeur != config.get(chemin)}


def _reglages_bruts(cle: str, reponse: str, config) -> dict:
    """Ce que la reponse designe, avant d avoir retire ce qui ne bouge pas."""
    from core import text_utils

    reponse = " ".join(str(reponse or "").split())
    question = PAR_CLE.get(cle)
    # Passer une question fermee ne veut pas dire « prends le premier
    # choix » : cela veut dire « laisse comme c est ».
    if question is not None and not question.libre and not reponse:
        return {}

    if cle == "langue":
        langue = reponse if reponse in ("fr", "en") else "fr"
        genre = prefs.genre_de_la_voix(str(config.get("voice.neural_voice", "")))
        return {
            "general.language": langue,
            "voice.stt_language": prefs.LANGUE_ECOUTEE[langue],
            "voice.neural_voice": prefs.voix_pour(langue, genre),
        }

    if cle == "voix":
        genre = "homme" if reponse == "homme" else "femme"
        langue = str(config.get("general.language", "fr"))[:2]
        return {"voice.neural_voice": prefs.voix_pour(langue, genre)}

    if cle == "nom_utilisateur":
        return {"general.user_name": _nom_propre(reponse)} if reponse else {}

    if cle == "nom_assistant":
        nom = _nom_propre(reponse)
        mot = text_utils.normalize(nom).strip()
        # Trop court, il serait confondu avec la moitie du dictionnaire :
        # on garde le nom en place plutot que d empecher d avancer.
        if len(mot) < 3:
            return {}
        return {"general.assistant_name": nom, "general.wake_word": mot}

    return {}


def _nom_propre(valeur: str) -> str:
    """« jarvis » -> « Jarvis ». Un nom deja capitalise n est pas touche."""
    valeur = " ".join(valeur.split())
    if valeur != valeur.lower():
        return valeur
    return " ".join(mot.capitalize() for mot in valeur.split())


def repondre(assistant, cle: str, reponse: str) -> dict:
    """
    Applique une reponse TOUT DE SUITE, et la retient.

    Question par question plutot qu en bloc a la fin : la langue choisie doit
    changer les trois questions suivantes, et un reglage deja donne est
    acquis meme si l application se ferme avant la derniere question.
    """
    reglages = reglages_pour(cle, reponse, assistant.config)
    if reglages:
        assistant.personnaliser(reglages)
    return reglages


def terminer(assistant) -> None:
    """Marque le premier lancement comme fait : il ne reviendra plus."""
    assistant.personnaliser({CLE_TERMINE: True})


def poser_en_texte(assistant, lire, ecrire) -> None:
    """
    Les memes questions, au clavier.

    `lire(invite)` rend une ligne, `ecrire(texte)` l affiche. Le mode texte
    de main.py les branche sur le terminal ; les tests sur des listes. Le
    panneau graphique, lui, pose exactement les memes questions autrement
    (voir gui.py) -- les deux chemins partagent QUESTIONS et `repondre`,
    jamais deux listes a tenir a jour.
    """
    for question in QUESTIONS:
        # Relue a chaque tour : la premiere question change la langue, et les
        # suivantes doivent se poser dans celle qui vient d etre choisie.
        langue = str(assistant.config.get("general.language", "fr"))[:2]
        ecrire("")
        ecrire(question.titre(langue))
        if question.aide(langue):
            ecrire("  " + question.aide(langue))
        if question.libre:
            invite = "  > " if not question.defaut else "  [" + question.defaut + "] > "
        else:
            for numero, possible in enumerate(question.choix, start=1):
                ecrire("  " + str(numero) + ". " + possible.libelle(langue))
            invite = "  > "
        reponse = _lire_reponse(question, lire(invite))
        repondre(assistant, question.cle, reponse)
    terminer(assistant)
    langue = str(assistant.config.get("general.language", "fr"))[:2]
    ecrire("")
    ecrire(bienvenue(assistant.name, langue))


def _lire_reponse(question: "Question", saisie: str) -> str:
    """
    Une question fermee accepte le numero ou le mot ; une question libre,
    tout ce qui est tape. Vide veut dire « passer », jamais « recommencer ».
    """
    saisie = " ".join(str(saisie or "").split())
    if question.libre:
        return saisie
    if saisie.isdigit():
        index = int(saisie) - 1
        if 0 <= index < len(question.choix):
            return question.choix[index].valeur
        return ""
    minuscule = saisie.lower()
    for possible in question.choix:
        if minuscule in (possible.valeur,
                         possible.libelle_fr.lower(), possible.libelle_en.lower()):
            return possible.valeur
    return ""


def bienvenue(nom: str, langue: str) -> str:
    """Le mot qui clot le premier lancement, une fois le nom connu."""
    if langue == "en":
        return ("All set. Say \"" + nom + "\" to wake me — and anything you just "
                "chose can be changed by asking me.")
    return ("Tout est prêt. Dites « " + nom + " » pour me réveiller — et tout ce "
            "que vous venez de choisir se change en me le demandant.")
