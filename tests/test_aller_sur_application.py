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
    fenetre(4, "Claude", "claude.exe"),
    # Le même navigateur, ouvert deux fois, sur deux écrans.
    fenetre(5, "Joueur du Grenier - Google Chrome", "chrome.exe", ecran=2),
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


# --------------------------------------------------------------------------
# L'écran de travail
# --------------------------------------------------------------------------
def test_la_fenetre_de_l_ecran_de_travail_est_choisie(assistant, bureau):
    """
    Le défaut constaté à l'usage. Chrome ouvert sur les deux écrans, l'écran 1
    choisi : ALMA affichait la fenêtre de l'écran 2 en annonçant « Voilà
    Chrome ». Vu de l'écran 1, elle disait une chose et en faisait une autre.
    """
    assistant.ecran_actif = 1
    assert assistant.handle("va sur Chrome").ok
    assert bureau["handle"] == 1


def test_l_autre_ecran_amene_l_autre_fenetre(assistant, bureau):
    assistant.ecran_actif = 2
    assistant.handle("va sur Chrome")
    assert bureau["handle"] == 5


def test_l_ecran_nomme_l_emporte_sur_l_ecran_de_travail(assistant, bureau):
    assistant.ecran_actif = 2
    assert assistant.handle("va sur Chrome sur l'écran 1").ok
    assert bureau["handle"] == 1


def test_sans_fenetre_sur_l_ecran_choisi_on_prend_celle_d_ailleurs(assistant, bureau):
    """Spotify n'est ouvert que sur l'écran 1 : mieux vaut l'afficher que rien."""
    assistant.ecran_actif = 2
    assistant.handle("va sur Spotify")
    assert bureau["handle"] == 2


@pytest.mark.parametrize("phrase", [
    "va sur l'écran 2", "écran 1", "passe sur le deuxième écran",
    "mets-toi sur l'écran 2", "reste sur l'écran 1", "travaille sur l'écran 2",
    "utilise l'écran 2", "le deuxième écran", "sur l'écran 2",
    "pour le premier écran", "va sur le premier écran",
])
def test_choisir_un_ecran_reste_intact(assistant, phrase):
    """
    Ne nommer que l'écran doit continuer de ne changer que l'écran : c'est le
    garde-fou qui distingue « va sur l'écran 1 » de « va sur Chrome sur
    l'écran 1 », et il ne doit pas mordre sur le premier.
    """
    assert commande(assistant, phrase) == "choisir_ecran"


# --------------------------------------------------------------------------
# Lever l'ambiguïté entre le logiciel et le site du même nom
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    # Sans précision, un nom qui figure dans la liste des sites désigne la
    # page : « va sur Google » veut le moteur, pas le navigateur.
    ("va sur Claude", "open_website"),
    ("va sur le site Claude", "open_website"),
    # Dire « l'application » tranche.
    ("va sur l'application Claude", "aller_sur_application"),
    ("affiche l'application Claude", "aller_sur_application"),
])
def test_dire_l_application_designe_le_logiciel(assistant, phrase, attendu):
    assert commande(assistant, phrase) == attendu


def test_l_application_nommee_ainsi_passe_bien_devant(assistant, bureau):
    reponse = assistant.handle("va sur l'application Claude")
    assert reponse.ok, reponse.text
    assert bureau["handle"] == 4


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
