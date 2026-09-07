"""
Volume de la vidéo contre volume de l'ordinateur.

Une vidéo de site de streaming a son propre niveau sonore. « baisse le volume
de la vidéo » doit agir sur le lecteur seul, « baisse le volume » sur toute la
machine — et les deux ne doivent jamais se confondre.
"""

import pytest

from core import desktop, media_control, win_utils
from core.context import Utterance


@pytest.fixture
def lecteur_sur_ecran_2(monkeypatch):
    """Une vidéo joue dans Chrome sur l'écran 2, rien sur l'écran 1."""
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=10, titre="Bloc-notes", processus="notepad.exe", ecran=1),
        desktop.Fenetre(handle=20, titre="Interstellar - YouTube - Google Chrome",
                        processus="chrome.exe", ecran=2),
    ])
    monkeypatch.setattr(media_control, "sessions", lambda: [
        media_control.SessionMedia("Chrome", "Interstellar", media_control.EN_LECTURE),
    ])


@pytest.fixture
def melangeur(monkeypatch):
    """Un mélangeur Windows factice : volume par application et volume général."""
    etat = {"chrome.exe": 100, "general": 50}
    monkeypatch.setattr(win_utils, "get_app_volume",
                        lambda nom: etat.get(nom))
    monkeypatch.setattr(win_utils, "set_app_volume",
                        lambda nom, n: etat.__setitem__(nom, max(0, min(100, int(n)))) or True)
    monkeypatch.setattr(win_utils, "change_app_volume",
                        lambda nom, d: etat.__setitem__(nom, max(0, min(100, etat[nom] + d)))
                        or etat[nom])
    monkeypatch.setattr(win_utils, "get_volume", lambda: etat["general"])
    monkeypatch.setattr(win_utils, "set_volume",
                        lambda n: etat.__setitem__("general", int(n)) or True)
    monkeypatch.setattr(win_utils, "change_volume",
                        lambda d: etat.__setitem__("general", etat["general"] + d)
                        or etat["general"])
    return etat


# --------------------------------------------------------------------------
# Les deux familles de phrases ne doivent pas se marcher dessus
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("baisse le volume de la vidéo à 30", "volume_media_set"),
    ("mets le volume du film à 60", "volume_media_set"),
    ("augmente le volume de la vidéo à 80", "volume_media_set"),
    ("baisse le volume de la vidéo", "volume_media_down"),
    ("mets la vidéo moins fort", "volume_media_down"),
    ("monte le volume de la vidéo", "volume_media_up"),
    ("mets le film plus fort", "volume_media_up"),
    # Sans objet, c'est le volume de l'ordinateur.
    ("baisse le volume à 30", "volume_set"),
    ("mets le volume à 30", "volume_set"),
    ("volume à 70", "volume_set"),
    ("monte le son", "volume_up"),
    ("baisse le son", "volume_down"),
    ("coupe le son", "volume_mute"),
])
def test_le_volume_vise_est_le_bon(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == attendu, phrase


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------
def test_le_volume_de_la_video_ne_touche_pas_celui_de_lordinateur(
        assistant, lecteur_sur_ecran_2, melangeur):
    assistant.definir_ecran(2)
    reponse = assistant.handle("baisse le volume de la vidéo à 30")
    assert reponse.ok, reponse.text
    assert melangeur["chrome.exe"] == 30
    assert melangeur["general"] == 50, "le volume général devait rester intact"


def test_le_volume_de_lordinateur_ne_touche_pas_celui_de_la_video(
        assistant, lecteur_sur_ecran_2, melangeur):
    assistant.definir_ecran(2)
    reponse = assistant.handle("mets le volume à 20")
    assert reponse.ok, reponse.text
    assert melangeur["general"] == 20
    assert melangeur["chrome.exe"] == 100, "le lecteur devait rester intact"


@pytest.mark.parametrize("depart,phrase,attendu", [
    (100, "monte le volume de la vidéo", 100),    # deja au maximum
    (100, "baisse le volume de la vidéo", 90),
    (50, "monte le volume de la vidéo", 60),
    (5, "baisse le volume de la vidéo", 0),       # jamais en dessous de zero
])
def test_les_paliers_de_dix(assistant, lecteur_sur_ecran_2, melangeur,
                            depart, phrase, attendu):
    melangeur["chrome.exe"] = depart
    assistant.definir_ecran(2)
    assert assistant.handle(phrase).ok
    assert melangeur["chrome.exe"] == attendu


def test_rien_ne_joue_sur_lecran_de_travail(assistant, lecteur_sur_ecran_2, melangeur):
    """Comme pour la pause : on ne va pas régler un lecteur d'un autre écran."""
    assistant.definir_ecran(1)
    reponse = assistant.handle("baisse le volume de la vidéo à 30")
    assert not reponse.ok
    assert "écran 1" in reponse.text
    assert melangeur["chrome.exe"] == 100, "le lecteur de l'écran 2 devait être épargné"


# --------------------------------------------------------------------------
# Reperage des sessions audio
# --------------------------------------------------------------------------
def test_une_application_est_reconnue_quelle_que_soit_son_ecriture(monkeypatch):
    class SessionFactice:
        def __init__(self, nom):
            self._nom = nom

        @property
        def Process(self):
            return type("P", (), {"name": lambda _self: self._nom})()

    monkeypatch.setattr(win_utils, "_sessions_audio", lambda: [
        SessionFactice("chrome.exe"), SessionFactice("firefox.exe"),
    ])
    assert len(win_utils.sessions_audio_de("Chrome")) == 1
    assert len(win_utils.sessions_audio_de("chrome.exe")) == 1
    assert len(win_utils.sessions_audio_de("Google Chrome")) == 1
    assert win_utils.sessions_audio_de("spotify.exe") == []
    assert win_utils.sessions_audio_de("") == []


def test_les_applications_qui_jouent_sont_rattachees_a_leur_ecran(lecteur_sur_ecran_2):
    assert media_control.applications_sur_ecran(2) == ["chrome.exe"]
    assert media_control.applications_sur_ecran(1) == []
