"""
Personnalisation : ce qu Alma retient de vous.

Un assistant qui vous appelle par votre prenom, qui porte le nom que vous
lui avez donne, qui parle votre langue avec la voix que vous preferez -- et
qui s en souvient au prochain lancement. Tout se dit en une phrase, rien ne
demande d ouvrir un fichier.

Chaque commande ici fait DEUX choses, et les deux comptent autant : appliquer
le reglage tout de suite, et le retenir. C est `assistant.personnaliser` qui
s en charge ; voir core/preferences.py pour l inventaire de ce qui se
personnalise, et pourquoi il est ecrit ailleurs que dans config.yaml.
"""

from __future__ import annotations

from core import preferences as prefs
from core.context import CommandContext, Response
from core.registry import command

# Les mots qui transforment une affirmation en question : « tu t'appelles
# comment ? » ne renomme personne. Sans cela, la reponse serait de s appeler
# « comment ».
INTERROGATIFS = ("comment", "quoi", "qui", "quel", "quelle", "what", "who",
                 "how", "which", "why")


def _est_une_question(valeur: str) -> bool:
    mots = valeur.strip().lower().split()
    return not mots or mots[0] in INTERROGATIFS


def _nom_propre(valeur: str) -> str:
    """
    Un nom prononce devient un nom ecrit : « jarvis » -> « Jarvis ».

    La transcription vocale rend rarement la majuscule, et un assistant qui
    s appelle « jarvis » en minuscules a l air d un bug. Un nom deja
    capitalise -- parce qu il a ete tape -- n est pas touche.
    """
    valeur = " ".join(valeur.split())
    if valeur != valeur.lower():
        return valeur
    return " ".join(mot.capitalize() for mot in valeur.split())


# --------------------------------------------------------------------------
# Identite
# --------------------------------------------------------------------------
@command(
    name="renommer_assistant",
    patterns=[
        r"^(?:appelle|appeler)\s+toi\s+(?:desormais\s+|maintenant\s+)?(.+)$",
        r"^tu\s+t\s+appelles?\s+(?:desormais\s+|maintenant\s+)?(.+)$",
        r"^(?:change|changer|modifie|modifier)\s+ton\s+(?:nouveau\s+)?nom\s+"
        r"(?:en|pour|par)\s+(.+)$",
        r"^ton\s+(?:nouveau\s+)?nom\s+(?:est|sera|c\s+est)\s+(?:desormais\s+)?(.+)$",
        r"^je\s+(?:veux|voudrais|vais)\s+t\s+appeler\s+(.+)$",
        r"^call\s+yourself\s+(.+)$",
        r"^your\s+(?:new\s+)?name\s+is\s+(?:now\s+)?(.+)$",
        r"^change\s+your\s+name\s+to\s+(.+)$",
        r"^i\s+(?:want|d\s+like)\s+to\s+call\s+you\s+(.+)$",
    ],
    category="Personnalisation",
    description="Donner un autre nom à l'assistant",
    examples=["appelle-toi Jarvis", "change ton nom en Jarvis",
              "call yourself Jarvis"],
    priority=99,
)
def renommer_assistant(ctx: CommandContext) -> Response:
    """
    Renomme l assistant, mot d appel compris.

    Les deux vont ensemble : un assistant qui s appelle Jarvis mais qui ne
    repond qu a « Alma » n a pas vraiment change de nom.
    """
    nom = _nom_propre(ctx.arg)
    if _est_une_question(nom):
        # « tu t'appelles comment ? » : la meme tournure, retournee. On y
        # repond plutot que de la refuser.
        actuel = ctx.assistant.name
        return ctx.reponse("Je m'appelle " + actuel + ".",
                           "My name is " + actuel + ".")
    from core import text_utils

    mot_appel = text_utils.normalize(nom).strip()
    if len(mot_appel) < 3:
        return ctx.erreur(
            "« " + nom + " » est trop court : je le confondrais avec d'autres mots. "
            "Choisissez un nom d'au moins trois lettres.",
            '"' + nom + '" is too short: I would confuse it with other words. '
            "Pick a name of at least three letters.",
        )
    ctx.assistant.personnaliser({
        "general.assistant_name": nom,
        "general.wake_word": mot_appel,
    })
    return ctx.reponse(
        "Je m'appelle " + nom + " maintenant, et je réponds à ce nom.",
        "My name is " + nom + " now, and I answer to it.",
    )


@command(
    name="nommer_utilisateur",
    patterns=[
        r"^(?:appelle|appeler)\s+moi\s+(?:desormais\s+|maintenant\s+)?(.+)$",
        r"^je\s+m\s+appelle\s+(.+)$",
        r"^mon\s+(?:pre)?nom\s+(?:est|c\s+est)\s+(.+)$",
        r"^tu\s+peux\s+m\s+appeler\s+(.+)$",
        r"^call\s+me\s+(.+)$",
        r"^my\s+(?:first\s+)?name\s+is\s+(.+)$",
        r"^i\s+am\s+called\s+(.+)$",
    ],
    category="Personnalisation",
    description="Dire à l'assistant comment vous appeler",
    examples=["appelle-moi Muneeb", "je m'appelle Muneeb", "call me Muneeb"],
    priority=99,
)
def nommer_utilisateur(ctx: CommandContext) -> Response:
    """Retient le prenom de l utilisateur, pour les salutations."""
    nom = _nom_propre(ctx.arg)
    if _est_une_question(nom):
        # « je m'appelle comment ? » : c est une question, pas un bapteme.
        connu = str(ctx.config.get("general.user_name", "") or "")
        if connu:
            return ctx.reponse("Vous m'avez dit de vous appeler " + connu + ".",
                               "You told me to call you " + connu + ".")
        return ctx.erreur("Vous ne me l'avez pas encore dit. Comment dois-je "
                          "vous appeler ?",
                          "You haven't told me yet. What should I call you?")
    ctx.assistant.personnaliser({"general.user_name": nom})
    return ctx.reponse("Entendu, " + nom + ". Je m'en souviendrai.",
                       "Got it, " + nom + ". I'll remember that.")


# --------------------------------------------------------------------------
# Langue et voix
# --------------------------------------------------------------------------
LANGUES = {
    "francais": "fr", "français": "fr", "french": "fr",
    "anglais": "en", "english": "en",
}


@command(
    name="changer_de_langue",
    patterns=[
        r"^(?:parle|parler|reponds|repondre|ecris)\s*(?:moi)?\s*(?:en|nous\s+en)\s+"
        r"(francais|anglais)$",
        r"^(?:passe|passer|bascule)\s+(?:en|au|a\s+l)\s+(francais|anglais)$",
        r"^(?:speak|answer|reply|write)\s*(?:to\s+me)?\s*(?:in\s+)?(french|english)$",
        r"^switch\s+to\s+(french|english)$",
    ],
    category="Personnalisation",
    description="Choisir la langue des réponses",
    examples=["parle-moi en anglais", "speak French", "switch to English"],
    priority=98,
)
def changer_de_langue(ctx: CommandContext) -> Response:
    """
    Change la langue des reponses, de l ecoute et de la voix.

    Les trois vont ensemble : repondre en anglais avec une voix francaise et
    une reconnaissance reglee sur le francais ne servirait a rien.
    """
    langue = LANGUES.get(ctx.arg.strip().lower(), "")
    if not langue:
        return ctx.erreur("Je ne connais que le français et l'anglais.",
                          "I only know French and English.")
    genre = prefs.genre_de_la_voix(str(ctx.config.get("voice.neural_voice", "")))
    ctx.assistant.personnaliser({
        "general.language": langue,
        "voice.stt_language": prefs.LANGUE_ECOUTEE[langue],
        "voice.neural_voice": prefs.voix_pour(langue, genre),
    })
    # La reponse se donne dans la langue DEMANDEE, pas dans celle de la
    # phrase : c est la premiere preuve que le changement a pris.
    if langue == "en":
        return Response(text="All right, I'll speak English from now on.")
    return Response(text="Très bien, je parlerai français à partir de maintenant.")


@command(
    name="couper_la_voix",
    patterns=[
        r"^(?:ne\s+)?parle\s+plus$",
        r"^(?:arrete|arreter)\s+de\s+parler$",
        r"^(?:ne\s+)?(?:dis|lis)\s+plus\s+rien$",
        r"^(?:coupe|couper|desactive)\s+(?:ta|la)\s+voix$",
        r"^(?:passe\s+en\s+)?mode\s+silencieux$",
        r"^stop\s+(?:talking|speaking|reading)(?:\s+out\s+loud)?$",
        r"^(?:don\s+t|do\s+not)\s+(?:speak|talk)\s+(?:any\s*more|again)$",
        r"^(?:silent|quiet)\s+mode$",
    ],
    category="Personnalisation",
    description="Ne plus lire les réponses à voix haute",
    examples=["ne parle plus", "mode silencieux", "stop talking"],
    priority=97,
)
def couper_la_voix(ctx: CommandContext) -> Response:
    """Les reponses restent affichees, mais ne sont plus lues."""
    ctx.assistant.personnaliser({"voice.speak_responses": False})
    return ctx.reponse("Entendu, je réponds par écrit maintenant.",
                       "Understood, I'll answer in writing from now on.")


@command(
    name="rendre_la_voix",
    patterns=[
        r"^(?:reparle|parle)\s+(?:a\s+voix\s+haute|de\s+nouveau|a\s+nouveau)$",
        r"^(?:remets|remettre|reactive|active)\s+(?:ta|la)\s+voix$",
        r"^(?:tu\s+peux\s+)?(?:reparler|parler)\s+a\s+voix\s+haute$",
        r"^(?:speak|talk)\s+(?:out\s+loud|again|to\s+me\s+again)$",
        r"^(?:turn|switch)\s+your\s+voice\s+back\s+on$",
    ],
    category="Personnalisation",
    description="Relire les réponses à voix haute",
    examples=["parle à voix haute", "remets ta voix", "speak out loud"],
    priority=97,
)
def rendre_la_voix(ctx: CommandContext) -> Response:
    """Retablit la lecture a voix haute."""
    ctx.assistant.personnaliser({"voice.speak_responses": True})
    return ctx.reponse("Me revoilà.", "I'm back.")


@command(
    name="changer_de_voix",
    patterns=[
        r"^(?:prends|prendre|mets|utilise)\s+(?:une\s+|la\s+)?voix\s+"
        r"(?:d\s+|de\s+)?(homme|femme|masculine|feminine)$",
        r"^(?:parle|parler)\s+avec\s+une\s+voix\s+(?:d\s+|de\s+)?"
        r"(homme|femme|masculine|feminine)$",
        r"^(?:je\s+veux\s+une\s+)?voix\s+(?:d\s+|de\s+)?"
        r"(homme|femme|masculine|feminine)$",
        r"^(?:use|take)\s+a\s+(male|female|man\s+s|woman\s+s)\s+voice$",
        r"^(?:speak|talk)\s+(?:with|in)\s+a\s+(male|female|man\s+s|woman\s+s)\s+voice$",
    ],
    category="Personnalisation",
    description="Choisir une voix d'homme ou de femme",
    examples=["prends une voix d'homme", "use a female voice"],
    priority=97,
)
def changer_de_voix(ctx: CommandContext) -> Response:
    """Change le timbre, en gardant la langue courante."""
    demande = ctx.arg.strip().lower()
    genre = "homme" if demande in ("homme", "masculine", "male", "man s") else "femme"
    langue = str(ctx.config.get("general.language", "fr"))[:2]
    ctx.assistant.personnaliser({"voice.neural_voice": prefs.voix_pour(langue, genre)})
    if genre == "homme":
        return ctx.reponse("Voilà ma voix d'homme.", "Here is my male voice.")
    return ctx.reponse("Voilà ma voix de femme.", "Here is my female voice.")


# Le debit, en trois crans : la voix neuronale le prend en pourcentage, la
# voix locale en mots par minute. Les deux sont regles ensemble, sinon le
# repli hors ligne parlerait a une autre vitesse.
DEBITS = {
    "vite": ("+25%", 210),
    "lent": ("-25%", 140),
    "normal": ("+0%", 175),
}


@command(
    name="changer_le_debit",
    patterns=[
        r"^(?:parle|parler)\s+(plus\s+vite|moins\s+vite|plus\s+lentement|"
        r"normalement|plus\s+doucement)$",
        r"^(?:speak|talk)\s+(faster|slower|more\s+slowly|normally|at\s+normal\s+speed)$",
    ],
    category="Personnalisation",
    description="Régler la vitesse de la voix",
    examples=["parle plus vite", "parle moins vite", "speak slower"],
    priority=97,
)
def changer_le_debit(ctx: CommandContext) -> Response:
    """Trois crans : plus vite, plus lentement, normalement."""
    demande = " ".join(ctx.arg.split()).lower()
    if demande in ("plus vite", "faster"):
        cran = "vite"
    elif demande in ("normalement", "normally", "at normal speed"):
        cran = "normal"
    else:
        cran = "lent"
    neuronal, local = DEBITS[cran]
    ctx.assistant.personnaliser({"voice.neural_rate": neuronal, "voice.rate": local})
    libelles = {
        "vite": ("Je parle plus vite.", "I'm speaking faster."),
        "lent": ("Je parle plus lentement.", "I'm speaking more slowly."),
        "normal": ("Je reprends mon débit normal.", "Back to my normal pace."),
    }
    return ctx.reponse(*libelles[cran])


# --------------------------------------------------------------------------
# Comportement
# --------------------------------------------------------------------------
@command(
    name="regler_les_confirmations",
    patterns=[
        r"^(?:ne\s+me\s+demande\s+plus|arrete\s+de\s+me\s+demander)\s+"
        r"(?:de\s+)?confirmation.*$",
        r"^(?:demande|demander)\s*(?:moi)?\s+(toujours|systematiquement)\s+"
        r"(?:une\s+)?confirmation.*$",
        r"^(?:stop|quit)\s+asking\s+(?:me\s+)?for\s+confirmation.*$",
        r"^(?:always|never)\s+ask\s+(?:me\s+)?(?:for\s+)?confirmation.*$",
    ],
    category="Personnalisation",
    description="Demander ou non une confirmation avant une action risquée",
    examples=["ne me demande plus confirmation",
              "demande-moi toujours confirmation",
              "always ask for confirmation"],
    priority=97,
)
def regler_les_confirmations(ctx: CommandContext) -> Response:
    """
    Active ou coupe la confirmation avant une action risquee.

    La couper vaut pour eteindre l ordinateur ou vider la corbeille : on le
    dit clairement, parce qu on ne revient pas d une corbeille videe.
    """
    norme = ctx.norm
    toujours = ("toujours" in norme or "systematiquement" in norme
                or "always" in norme)
    ctx.assistant.personnaliser({"general.confirm_dangerous_actions": toujours})
    if toujours:
        return ctx.reponse("D'accord, je demanderai toujours avant d'agir.",
                           "All right, I'll always ask before acting.")
    return ctx.reponse(
        "Entendu, j'agirai sans demander — y compris pour éteindre l'ordinateur "
        "ou vider la corbeille.",
        "Understood, I'll act without asking — including shutting the computer "
        "down or emptying the recycle bin.",
    )


@command(
    name="regler_duree_ecoute",
    patterns=[
        r"^(?:reste|rester)\s+(?:eveille|reveille|a\s+l\s+ecoute|attentif)\s+"
        r"(?:pendant\s+)?(\d+)\s*(?:secondes?|minutes?|s|min)?$",
        r"^(?:ecoute|ecouter)\s+(?:moi\s+)?(?:pendant\s+)?(\d+)\s*"
        r"(?:secondes?|minutes?|s|min)$",
        r"^stay\s+(?:awake|listening)\s+(?:for\s+)?(\d+)\s*"
        r"(?:seconds?|minutes?|s|min)?$",
    ],
    category="Personnalisation",
    description="Régler combien de temps l'assistant reste éveillé",
    examples=["reste éveillé 2 minutes", "stay awake for 30 seconds"],
    priority=97,
)
def regler_duree_ecoute(ctx: CommandContext) -> Response:
    """Combien de temps Alma reste receptif apres avoir ete appele."""
    valeur = int(ctx.arg or 0)
    # « 2 » veut dire deux minutes, « 90 » veut dire quatre-vingt-dix
    # secondes : personne ne demande deux secondes d ecoute, ni quatre-vingt-
    # dix minutes. L unite dite dans la phrase tranche quand elle y est.
    if "minute" in ctx.norm or (valeur <= 10 and "second" not in ctx.norm):
        valeur *= 60
    secondes = max(5, min(900, valeur))
    ctx.assistant.personnaliser({"voice.armed_seconds": secondes})
    return ctx.reponse(
        "Je resterai à l'écoute " + str(secondes) + " secondes après votre appel.",
        "I'll stay listening for " + str(secondes) + " seconds after you call me.",
    )


# Les crans de sensibilite du micro, du plus sourd au plus fin. Le defaut
# (0,0004) est le deuxieme : il y a donc de la marge des deux cotes.
SENSIBILITES = (0.0015, 0.0004, 0.0002, 0.0001)


@command(
    name="regler_sensibilite",
    patterns=[
        r"^(?:sois|soit|deviens)\s+(plus|moins)\s+sensible.*$",
        r"^(?:tu\s+m\s+entends\s+mal|tu\s+ne\s+m\s+entends\s+pas)$",
        r"^(?:be|get)\s+(more|less)\s+sensitive.*$",
        r"^you\s+(?:can\s+t|cannot|don\s+t)\s+hear\s+me$",
    ],
    category="Personnalisation",
    description="Rendre le micro plus ou moins sensible",
    examples=["sois plus sensible", "tu m'entends mal", "be less sensitive"],
    priority=97,
)
def regler_sensibilite(ctx: CommandContext) -> Response:
    """Descend ou remonte d un cran le seuil de detection de la voix."""
    actuel = float(ctx.config.get("voice.min_threshold", 0.0004) or 0.0004)
    # « tu m'entends mal » ne nomme pas de direction : c est une plainte, et
    # la reponse est toujours d ecouter mieux.
    moins = "moins" in ctx.norm or "less" in ctx.norm
    proche = min(range(len(SENSIBILITES)),
                 key=lambda i: abs(SENSIBILITES[i] - actuel))
    index = max(0, min(len(SENSIBILITES) - 1, proche + (-1 if moins else 1)))
    if index == proche:
        return ctx.erreur(
            "Je suis déjà au maximum de ce côté-là.",
            "I'm already as far as I go in that direction.",
        )
    ctx.assistant.personnaliser({"voice.min_threshold": SENSIBILITES[index]})
    if moins:
        return ctx.reponse("D'accord, je me déclencherai moins facilement.",
                           "All right, I'll trigger less easily.")
    return ctx.reponse("D'accord, j'ouvre plus grand les oreilles.",
                       "All right, I'll listen harder.")


# --------------------------------------------------------------------------
# Contenu
# --------------------------------------------------------------------------
@command(
    name="regler_ma_ville",
    patterns=[
        r"^(?:ma\s+ville\s+(?:est|c\s+est)|je\s+suis\s+a|j\s+habite\s+a?)\s+(.+)$",
        r"^(?:my\s+city\s+is|i\s+live\s+in|i\s+m\s+in)\s+(.+)$",
    ],
    category="Personnalisation",
    description="Retenir votre ville, pour la météo",
    examples=["ma ville c'est Bruxelles", "j'habite à Paris",
              "my city is Brussels"],
    priority=96,
)
def regler_ma_ville(ctx: CommandContext) -> Response:
    """La ville utilisee par « quel temps fait-il » sans precision."""
    ville = _nom_propre(ctx.arg)
    if _est_une_question(ville):
        return ctx.erreur("Dans quelle ville êtes-vous ?", "Which city are you in?")
    ctx.assistant.personnaliser({"weather.default_city": ville})
    return ctx.reponse(
        "C'est noté : " + ville + ". La météo s'y rapportera par défaut.",
        "Noted: " + ville + ". The weather will default to it.",
    )


@command(
    name="regler_dossier_musique",
    patterns=[
        r"^ma\s+musique\s+(?:est|se\s+trouve)\s+dans\s+(.+)$",
        r"^(?:mon\s+)?dossier\s+(?:de\s+)?musique\s+(?:est|c\s+est)\s+(.+)$",
        r"^my\s+music\s+(?:is\s+)?(?:in|folder\s+is)\s+(.+)$",
    ],
    category="Personnalisation",
    description="Indiquer où se trouve votre musique",
    examples=["ma musique est dans D:/Musique", "my music is in D:/Music"],
    priority=96,
)
def regler_dossier_musique(ctx: CommandContext) -> Response:
    """Le dossier ou « mets de la musique » ira chercher un fichier."""
    from pathlib import Path

    from core import win_utils

    # ctx.arg vient de la chaine d ORIGINE : le chemin garde ses separateurs
    # et sa casse, que la normalisation aurait effaces.
    dossier = ctx.arg.strip().strip('"').strip("'")
    if not dossier:
        return ctx.erreur("Quel dossier ?", "Which folder?")
    if not Path(win_utils.expand(dossier)).is_dir():
        return ctx.erreur("Je ne trouve pas le dossier « " + dossier + " ».",
                          'I can\'t find the folder "' + dossier + '".')
    ctx.assistant.personnaliser({"paths.music": dossier})
    return ctx.reponse("C'est noté : votre musique est dans " + dossier + ".",
                       "Noted: your music is in " + dossier + ".")


# --------------------------------------------------------------------------
# Revoir et oublier
# --------------------------------------------------------------------------
@command(
    name="mes_preferences",
    informatif=True,
    patterns=[
        r"(?:quelles?\s+sont\s+)?mes\s+(?:preferences|reglages|personnalisations)",
        r"^(?:tes|vos)\s+reglages$",
        # « qu'est-ce que tu sais sur moi » n'est PAS ici : cela demande les
        # faits retenus (commands/memoire.py), pas les reglages.
        r"(?:what\s+are\s+)?my\s+(?:preferences|settings)",
    ],
    keywords=[["mes", "preferences"], ["my", "preferences"]],
    category="Personnalisation",
    description="Lister ce que l'assistant a retenu de vous",
    examples=["quelles sont mes préférences", "what are my preferences"],
    priority=95,
)
def mes_preferences(ctx: CommandContext) -> Response:
    """Montre les reglages personnalises, et eux seuls."""
    # Les reglages derives (le mot d appel, la langue d ecoute) sont retenus
    # mais pas montres : ils ne font que redire une decision deja listee.
    retenues = {chemin: valeur
                for chemin, valeur in ctx.assistant.preferences.charger().items()
                if prefs.PAR_CHEMIN[chemin].visible}
    anglais = ctx.lang == "en"
    if not retenues:
        return ctx.reponse(
            "Je n'ai encore rien retenu de particulier. Dites par exemple "
            "« appelle-moi Muneeb » ou « appelle-toi Jarvis ».",
            'I haven\'t learned anything specific yet. Say for example '
            '"call me Muneeb" or "call yourself Jarvis".',
        )
    lignes = ["What I've learned about you:" if anglais else "Ce que j'ai retenu de vous :"]
    for chemin, valeur in sorted(retenues.items()):
        reglage = prefs.PAR_CHEMIN.get(chemin)
        if reglage is None:
            continue
        lignes.append("  " + reglage.libelle(ctx.lang) + " : "
                      + _lisible(chemin, valeur, ctx.lang) + reglage.unite(ctx.lang))
    ctx.assistant.io.write("\n".join(lignes))
    return ctx.reponse(
        "J'ai retenu " + str(len(retenues)) + " réglages, ils sont à l'écran.",
        "I've kept " + str(len(retenues)) + " settings, they're on screen.",
    )


def _lisible(chemin: str, valeur, langue: str) -> str:
    """
    La valeur telle qu on la dit, pas telle qu elle est stockee.

    « True » et « fr-FR-HenriNeural » sont justes dans un fichier ; ils ne
    repondent pas a quelqu un qui demande ce qu on a retenu de lui.
    """
    anglais = langue == "en"
    if isinstance(valeur, bool):
        if anglais:
            return "yes" if valeur else "no"
        return "oui" if valeur else "non"
    if chemin == "voice.neural_voice":
        genre = prefs.genre_de_la_voix(str(valeur))
        if anglais:
            return "a male voice" if genre == "homme" else "a female voice"
        return "une voix d'homme" if genre == "homme" else "une voix de femme"
    if chemin == "general.language":
        langues = {"fr": ("le français", "French"), "en": ("l'anglais", "English")}
        dit = langues.get(str(valeur))
        if dit:
            return dit[1] if anglais else dit[0]
    return str(valeur)


@command(
    name="oublier_preferences",
    patterns=[
        r"^(?:oublie|oublier)\s+(?:mes|tes)\s+(?:preferences|reglages|personnalisations)$",
        r"^(?:remets|remettre|restaure|reinitialise)\s+(?:les|tes)\s+reglages"
        r"(?:\s+par\s+defaut)?$",
        r"^(?:reviens|revenir)\s+(?:a|aux)\s+(?:tes\s+)?reglages?\s+(?:d\s+origine|par\s+defaut)$",
        r"^forget\s+(?:my|your)\s+(?:preferences|settings)$",
        r"^reset\s+(?:your\s+)?settings(?:\s+to\s+default)?$",
        r"^(?:go\s+)?back\s+to\s+(?:the\s+)?default\s+settings$",
    ],
    category="Personnalisation",
    description="Oublier toutes les personnalisations",
    examples=["oublie mes préférences", "remets les réglages par défaut",
              "reset your settings"],
    priority=96,
)
def oublier_preferences(ctx: CommandContext) -> Response:
    """
    Revient a la configuration d origine.

    Le nom d Alma en fait partie : on le dit, sinon l utilisateur appellerait
    encore « Jarvis » sans obtenir de reponse.
    """
    if not ctx.confirm("Oublier toutes vos personnalisations ?",
                       "Forget all your personalizations?"):
        return ctx.reponse("Je ne touche à rien.", "I'm leaving everything as is.")
    combien = ctx.assistant.oublier_personnalisations()
    if not combien:
        return ctx.reponse("Il n'y avait rien à oublier.",
                           "There was nothing to forget.")
    nom = ctx.assistant.name
    return ctx.reponse(
        str(combien) + " réglages oubliés. Je m'appelle de nouveau " + nom + ".",
        str(combien) + " settings forgotten. My name is " + nom + " again.",
    )
