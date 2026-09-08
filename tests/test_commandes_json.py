"""
Le fichier commandes.json est la spécification : ce test le fait respecter.

Chaque phrase qui y figure doit atteindre une commande réelle. Si une phrase
est ajoutée au fichier sans que le code la comprenne, ce test échoue — c'est
ce qui empêche la spécification et le code de diverger en silence.
"""

import json
from pathlib import Path

import pytest

from core.context import Utterance
from core.registry import all_commands

FICHIER = Path(__file__).resolve().parent.parent / "commandes.json"

# Valeurs concrètes pour les emplacements X / Y du fichier.
REMPLACEMENTS = {
    "ouvre X": "ouvre YouTube",
    "ouvre un nouvel onglet X": "ouvre un nouvel onglet YouTube",
    "ouvre X dans un nouvel onglet": "ouvre YouTube dans un nouvel onglet",
    "va sur X": "va sur YouTube",
    "reviens sur X": "reviens sur YouTube",
    "affiche l'onglet X": "affiche l'onglet YouTube",
    "va sur X et mets Y": "va sur Netflix et mets Interstellar",
    "va sur X et recherche Y": "va sur Netflix et recherche Interstellar",
    "mets X sur Y": "mets Interstellar sur Netflix",
    "cherche X sur Y": "cherche Interstellar sur Netflix",
    "recherche X sur Y": "recherche Interstellar sur Netflix",
    "mets pause à la X": "mets pause à la vidéo",
    "fais pause à la X": "fais pause à la vidéo",
    "mets la X en pause": "mets la vidéo en pause",
    "pause la X": "pause la vidéo",
    "mets la série X": "mets la série The Flash",
    "lance le film X sur Y": "lance le film Interstellar sur Netflix",
    "regarde le documentaire X": "regarde le documentaire Cosmos",
    "reviens à l'accueil de X": "reviens à l'accueil de Netflix",
    "va sur l écran X": "va sur l'écran 2",
    "écran X": "écran 2",
    "mets toi sur l écran X": "mets toi sur l'écran 2",
    "sur l écran X": "sur l'écran 2",
}

# Commandes qui n'ont de sens que dans une situation précise : vérifiées
# séparément, avec cette situation.
CONTEXTUELLES = {"Arrêter le défilement en cours"}


def charger():
    with open(FICHIER, encoding="utf-8") as f:
        return json.load(f)["actions"]


def concretiser(phrase):
    return REMPLACEMENTS.get(phrase, phrase)


def cas():
    """Une entrée de test par phrase du fichier."""
    for entree in charger():
        if entree["action"] in CONTEXTUELLES:
            continue
        for phrase in entree["phrases"]:
            yield pytest.param(concretiser(phrase), entree["action"],
                               id=concretiser(phrase))


def test_le_fichier_existe_et_est_lisible():
    assert FICHIER.exists(), "commandes.json est la spécification du projet"
    actions = charger()
    assert len(actions) > 80
    assert all(a["phrases"] for a in actions), "une action sans phrase ne sert à rien"


@pytest.mark.parametrize("phrase,action", list(cas()))
def test_chaque_phrase_du_fichier_atteint_une_commande(router, config, phrase, action):
    utterance = Utterance.parse(phrase, wake_words=config.get("general.wake_words"))
    resolution = router.resolve(utterance, None)
    assert resolution is not None, "« " + phrase + " » ne déclenche rien (" + action + ")"


def test_chaque_phrase_atteint_la_commande_annoncee(router, config):
    """
    Quand l'intention décrite correspond à une commande existante, les phrases
    doivent bien y mener — pas seulement mener quelque part.
    """
    par_description = {c.description: c.name for c in all_commands()}
    ecarts = []
    for entree in charger():
        attendu = par_description.get(entree["action"])
        if attendu is None or entree["action"] in CONTEXTUELLES:
            continue
        for phrase in entree["phrases"]:
            concret = concretiser(phrase)
            utterance = Utterance.parse(concret, wake_words=config.get("general.wake_words"))
            resolution = router.resolve(utterance, None)
            obtenu = resolution.command.name if resolution else "aucune"
            if obtenu != attendu:
                ecarts.append(concret + " -> " + obtenu + " (voulu " + attendu + ")")
    assert not ecarts, "phrases mal dirigées :\n" + "\n".join(ecarts)


def test_arreter_le_defilement_pendant_un_defilement(assistant, router):
    """La seule phrase du fichier qui dépende d'une situation en cours."""
    from core import desktop, interaction

    fenetre = desktop.Fenetre(handle=1, titre="Page - Chrome",
                              processus="chrome.exe", ecran=1)
    interaction_molette = interaction._molette
    interaction._molette = lambda n: None
    try:
        assistant.defilement.demarrer(fenetre, intervalle=0.05)
        utterance = Utterance.parse("arrête",
                                    wake_words=assistant.config.get("general.wake_words"))
        resolution = router.resolve(utterance, assistant)
        assert resolution is not None
        assert resolution.command.name == "arreter_defilement"
    finally:
        assistant.defilement.arreter()
        interaction._molette = interaction_molette
