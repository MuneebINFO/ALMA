"""
Tests d'EXÉCUTION des commandes de lecture et de pause.

Les tests de routage ne suffisent pas : ils vérifient qu'une phrase atteint le
bon handler, jamais que ce handler s'exécute. Une commande peut donc router
parfaitement et planter à l'appel — c'est exactement ce qui est arrivé avec
un `Response.action()` qui n'existait plus.
"""

import re
from pathlib import Path

import pytest

from core import desktop, media_control
from core.context import Response

RACINE = Path(__file__).resolve().parent.parent


def fenetre(titre, processus, ecran, handle=1):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


def session(app, joue, titre="un contenu"):
    return media_control.SessionMedia(
        app, titre, media_control.EN_LECTURE if joue else media_control.EN_PAUSE
    )


@pytest.fixture
def sessions_factices(monkeypatch):
    """Deux lecteurs déclarés sur l'écran 1, un en lecture et un en pause."""
    actions = []
    monkeypatch.setattr(media_control, "sessions",
                        lambda: [session("Chrome", True), session("Spotify", False)])
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("YouTube - Google Chrome", "chrome.exe", 1, handle=10),
        fenetre("Spotify", "spotify.exe", 1, handle=11),
    ])
    monkeypatch.setattr(media_control, "_agir_sur_session",
                        lambda app, action: actions.append((app, action)) or True)
    return actions


def test_lancer_la_video_relance_ce_qui_est_en_pause(assistant, sessions_factices):
    reponse = assistant.handle("lance la vidéo")
    assert reponse.ok, reponse.text
    assert ("Spotify", "play") in sessions_factices
    assert ("Chrome", "play") not in sessions_factices, "ne pas relancer ce qui joue déjà"


def test_mettre_en_pause_narrete_que_ce_qui_joue(assistant, sessions_factices):
    reponse = assistant.handle("mets pause à la vidéo")
    assert reponse.ok, reponse.text
    assert ("Chrome", "pause") in sessions_factices
    assert ("Spotify", "pause") not in sessions_factices, "déjà en pause"


@pytest.mark.parametrize("phrase", [
    "lance la vidéo", "joue la vidéo", "démarre la vidéo", "remets la vidéo",
    "mets pause à la vidéo", "mets la vidéo en pause", "pause la vidéo",
    "mets pause à la musique",
])
def test_toutes_les_formulations_s_executent_sans_erreur(assistant, sessions_factices, phrase):
    """Le test qui manquait : exécuter, pas seulement router."""
    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " -> " + reponse.text


def test_ces_actions_ne_sont_pas_lues_a_voix_haute(assistant, sessions_factices):
    """Leur effet s'entend : les annoncer n'apporte rien."""
    assert assistant.handle("lance la vidéo").speak is False
    assert assistant.handle("mets pause à la vidéo").speak is False


def test_aucune_methode_de_reponse_inexistante_nest_appelee():
    """
    Garde-fou général : toute méthode `Response.xxx()` utilisée dans le code
    doit exister. C'est ce contrôle qui aurait évité l'appel à
    `Response.action()`, supprimée du projet mais encore référencée.
    """
    manquantes = []
    for dossier in ("commands", "core"):
        for fichier in (RACINE / dossier).rglob("*.py"):
            source = fichier.read_text(encoding="utf-8")
            for nom in set(re.findall(r"\bResponse\.([a-zA-Z_]\w*)\s*\(", source)):
                if not hasattr(Response, nom):
                    manquantes.append(str(fichier.relative_to(RACINE)) + " : Response." + nom)
    assert not manquantes, "méthodes inexistantes :\n" + "\n".join(sorted(manquantes))


# --------------------------------------------------------------------------
# Confinement a l ecran de travail
# --------------------------------------------------------------------------
@pytest.fixture
def video_sur_ecran_2(monkeypatch):
    """Une vidéo joue sur l'écran 2 ; l'écran 1 n'a qu'un éditeur de texte."""
    actions = []
    monkeypatch.setattr(media_control, "sessions",
                        lambda: [session("Chrome", True, "Interstellar")])
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Bloc-notes", "notepad.exe", 1, handle=10),
        fenetre("Interstellar - YouTube - Google Chrome", "chrome.exe", 2, handle=20),
    ])
    monkeypatch.setattr(media_control, "_agir_sur_session",
                        lambda app, action: actions.append((app, action)) or True)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan",
                        lambda h: actions.append(("premier_plan", h)) or True)
    return actions


@pytest.mark.parametrize("phrase", [
    "mets pause à la vidéo", "pause", "lance la vidéo", "chanson suivante",
])
def test_rien_a_faire_quand_la_lecture_est_sur_un_autre_ecran(
        assistant, video_sur_ecran_2, phrase):
    """
    Le bug signalé : l'assistant travaille sur l'écran 1, la vidéo joue sur
    l'écran 2. Il ne doit rien toucher du tout.
    """
    assistant.definir_ecran(1)
    reponse = assistant.handle(phrase)
    assert not reponse.ok, phrase + " -> " + reponse.text
    assert video_sur_ecran_2 == [], phrase + " a agi hors de l'écran 1"


def test_la_meme_phrase_agit_apres_etre_alle_sur_l_ecran_2(assistant, video_sur_ecran_2):
    """Et une fois sur le bon écran, la commande fonctionne."""
    assistant.definir_ecran(2)
    reponse = assistant.handle("mets pause à la vidéo")
    assert reponse.ok, reponse.text
    assert ("Chrome", "pause") in video_sur_ecran_2


def test_une_session_est_rattachee_a_la_fenetre_qui_porte_son_titre(monkeypatch):
    """
    Chrome n'expose qu'une session pour toutes ses fenêtres : c'est le titre
    qui dit laquelle joue.
    """
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Gmail - Google Chrome", "chrome.exe", 1, handle=10),
        fenetre("Interstellar - YouTube - Google Chrome", "chrome.exe", 2, handle=20),
    ])
    monkeypatch.setattr(media_control, "sessions",
                        lambda: [session("Chrome", True, "Interstellar")])
    assert media_control.sessions_sur_ecran(1) == []
    assert len(media_control.sessions_sur_ecran(2)) == 1


def test_un_lecteur_sans_fenetre_reste_pilotable(monkeypatch):
    """Spotify réduit dans la zone de notification n'est sur aucun écran."""
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Bloc-notes", "notepad.exe", 1, handle=10),
    ])
    monkeypatch.setattr(media_control, "sessions",
                        lambda: [session("Spotify", True, "une chanson")])
    assert len(media_control.sessions_sur_ecran(1)) == 1


def test_une_fenetre_de_navigateur_ordinaire_ne_declenche_rien(assistant, monkeypatch):
    """
    L'écran 1 n'affiche qu'une boîte mail : envoyer « espace » ferait défiler
    la page. La vidéo de l'écran 2 ne doit pas bouger non plus.
    """
    actions = []
    monkeypatch.setattr(media_control, "sessions",
                        lambda: [session("Chrome", True, "Interstellar")])
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Boîte de réception - Gmail - Google Chrome", "chrome.exe", 1, handle=10),
        fenetre("Interstellar - YouTube - Google Chrome", "chrome.exe", 2, handle=20),
    ])
    monkeypatch.setattr(media_control, "_agir_sur_session",
                        lambda app, action: actions.append((app, action)) or True)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan",
                        lambda h: actions.append(("premier_plan", h)) or True)

    assistant.definir_ecran(1)
    reponse = assistant.handle("mets pause à la vidéo")
    assert not reponse.ok
    assert actions == []
