"""
« va sur Chrome » : aller sur une application déjà ouverte.

Le cas signalé à l'usage — et qui n'a jamais marché : « va sur X » ne visait
que les sites web. Une application n'était atteignable que par « ouvre X »,
qui en lançait une deuxième au lieu d'afficher celle qui tournait.
"""

import pytest

from core import desktop
from core.context import Response, Utterance


def fenetre(handle, titre, processus, ecran=1):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


OUVERTES = [
    fenetre(1, "Gagner de l'argent avec l'IA - Google Chrome", "chrome.exe"),
    fenetre(2, "Spotify Premium", "Spotify.exe"),
    fenetre(3, "alma.py - Visual Studio Code", "Code.exe"),
]


@pytest.fixture
def bureau(monkeypatch):
    """Un bureau connu, et le premier plan qui retient qui on lui donne."""
    devant = {"handle": None}
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: list(OUVERTES))

    def au_premier_plan(handle):
        devant["handle"] = handle
        return True

    monkeypatch.setattr(desktop, "mettre_au_premier_plan", au_premier_plan)
    return devant


def commande(assistant, phrase):
    resolution = assistant.router.resolve(
        Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words")),
        assistant=assistant,
    )
    return resolution.command.name if resolution else "aucune"


# --------------------------------------------------------------------------
# Aller sur une application ouverte
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,handle", [
    ("va sur Chrome", 1),
    ("affiche Chrome", 1),
    ("montre Chrome", 1),
    ("bascule sur Chrome", 1),
    ("passe sur Spotify", 2),
    # L'exécutable ne porte pas toujours le nom du logiciel : Visual Studio
    # Code s'exécute sous « Code.exe », et c'est le titre qui le rattrape.
    ("va sur Visual Studio Code", 3),
])
def test_la_fenetre_ouverte_passe_devant(assistant, bureau, phrase, handle):
    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " : " + reponse.text
    assert bureau["handle"] == handle


def test_aller_sur_une_application_ne_se_commente_pas(assistant, bureau):
    assert assistant.handle("va sur Chrome").speak is False


def test_une_application_fermee_est_ouverte(assistant, bureau, monkeypatch):
    """« va sur X » veut voir X ; s'il n'est pas là, l'ouvrir revient au même."""
    lancees = []

    def ouvrir(ctx):
        lancees.append(ctx.arg)
        return Response(text="ouvert")

    monkeypatch.setattr("commands.apps.open_app", ouvrir)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [])
    assistant.handle("va sur Spotify")
    assert lancees == ["Spotify"]


# --------------------------------------------------------------------------
# Ce que la nouvelle commande ne doit surtout pas capter
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("va sur YouTube", "open_website"),
    ("va sur Netflix", "open_website"),
    ("va sur Google", "open_website"),
    ("va sur l'écran 2", "choisir_ecran"),
    ("va sur le bureau", "afficher_bureau"),
    ("ouvre Chrome", "open_app"),
    ("ferme Chrome", "close_app"),
])
def test_les_voisins_gardent_leur_commande(assistant, phrase, attendu):
    assert commande(assistant, phrase) == attendu


@pytest.mark.parametrize("phrase", [
    "passe", "suivant", "chanson suivante", "passe à la chanson suivante",
    "passe la musique", "passe au suivant", "change de musique", "skip",
])
def test_passer_au_morceau_suivant_reste_intact(assistant, phrase):
    """
    « passe » seul veut dire « morceau suivant ». Suivi de quelque chose, il
    veut souvent dire « va sur » : « passe sur Spotify » demandait la piste
    suivante.
    """
    assert commande(assistant, phrase) == "media_next"
