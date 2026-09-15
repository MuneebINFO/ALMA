"""
Ce qu Alma dit PENDANT qu elle travaille.

Une commande qui repond en trente millisecondes n a rien a annoncer : la
reponse arrive avant l annonce. Mais quand il faut aller chercher sur
internet, attendre l application Claude ou analyser une image, le silence
ne se distingue pas d une panne -- et c est tout le probleme : on ne sait
pas si la demande est partie.

D ou une phrase, dite AVANT le travail et non a la place : « je cherche »,
puis la reponse. Deux secondes plus tard ou dix, on sait au moins que
quelque chose se passe.

Une commande declare ce qu elle fait attendre avec `attente="recherche"`
(voir core/registry.py). Rien a declarer signifie : c est immediat, on se
tait. C est le cas de l immense majorite.
"""

from __future__ import annotations

import random

# Les genres d attente, et ce qui se dit pour chacun. Plusieurs formulations
# par genre : la meme phrase a chaque fois se remarque au bout de trois fois.
#
# Toutes sont COURTES. Elles passent avant une reponse qui va arriver, et une
# annonce plus longue que ce qu elle annonce n a plus de sens.
ANNONCES = {
    # Aller chercher dehors : internet, Wikipedia, la recherche Google.
    "recherche": (
        ("Je cherche.", "Un instant, je cherche.", "Je regarde ça."),
        ("Looking it up.", "One moment, looking it up.", "Let me check."),
    ),
    # Attendre un modele : l application Claude, le CLI, un modele local.
    "reflexion": (
        ("Je réfléchis.", "Un instant.", "Je m'en occupe."),
        ("Thinking.", "One moment.", "On it."),
    ),
    # Regarder quelque chose : une image, un écran, un document.
    "analyse": (
        ("J'analyse.", "Je regarde ça.", "Analyse en cours."),
        ("Analysing.", "Let me look at that.", "Analysing now."),
    ),
    # Parcourir un site, cliquer, attendre un chargement.
    "navigation": (
        ("J'y vais.", "Je m'en occupe.", "Un instant."),
        ("On my way.", "On it.", "One moment."),
    ),
}

GENRES = tuple(ANNONCES)


def annonce(genre: str, langue: str = "fr") -> str:
    """
    Une phrase d attente pour ce genre de travail, dans cette langue.

    Chaine vide si le genre est inconnu : une annonce ratee ne doit jamais
    empecher la commande de s executer.
    """
    formulations = ANNONCES.get(genre)
    if not formulations:
        return ""
    return random.choice(formulations[1 if langue == "en" else 0])
