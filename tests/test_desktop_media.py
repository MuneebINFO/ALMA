"""
Tests du ciblage par écran et de la réutilisation d'onglet.

Aucun test ne pilote réellement le bureau : les appels Windows sont remplacés
par des doublures. On vérifie la logique de décision, pas l'API Windows.
"""

import pytest

from core import desktop, media_control


class FenetreFactice(desktop.Fenetre):
    pass


def fenetre(titre, processus, ecran, handle=1):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


# --------------------------------------------------------------------------
# Reconnaissance des applications
# --------------------------------------------------------------------------
@pytest.mark.parametrize("processus,attendu", [
    ("chrome.exe", True), ("firefox.exe", True), ("msedge.exe", True),
    ("spotify.exe", False), ("notepad.exe", False),
])
def test_detection_des_navigateurs(processus, attendu):
    assert fenetre("x", processus, 1).est_navigateur is attendu


@pytest.mark.parametrize("processus,session,attendu", [
    ("chrome.exe", "Chrome", True),
    ("Chrome.exe", "chrome", True),
    ("spotify.exe", "Spotify", True),
    ("firefox.exe", "Chrome", False),
    ("", "Chrome", False),
])
def test_correspondance_processus_session(processus, session, attendu):
    """Une fenêtre doit être reliée à la bonne session média."""
    assert media_control.correspond(processus, session) is attendu


# --------------------------------------------------------------------------
# Ciblage par ecran
# --------------------------------------------------------------------------
def test_pause_ecran_vise_la_bonne_application(monkeypatch):
    """
    Deux lecteurs jouent sur deux écrans différents : seul celui de l'écran
    demandé doit être mis en pause.
    """
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Netflix - Chrome", "chrome.exe", 1, handle=10),
        fenetre("Twitch - Firefox", "firefox.exe", 2, handle=20),
    ])
    monkeypatch.setattr(media_control, "sessions", lambda: [
        media_control.SessionMedia("Chrome", "Un film", media_control.EN_LECTURE),
        media_control.SessionMedia("Firefox", "Un stream", media_control.EN_LECTURE),
    ])
    agies = []
    monkeypatch.setattr(media_control, "_agir_sur_session",
                        lambda app, action: agies.append((app, action)) or True)

    ok, detail = media_control.agir_sur_ecran(2, "pause")
    assert ok
    assert agies == [("Firefox", "pause")], "seul l'écran 2 devait être touché"
    assert "Firefox" in detail


def test_pause_ecran_sans_lecture_ne_fait_rien(monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Bloc-notes", "notepad.exe", 1),
    ])
    monkeypatch.setattr(media_control, "sessions", lambda: [])
    ok, detail = media_control.agir_sur_ecran(1, "pause")
    assert not ok
    assert "lecture" in detail


def test_pause_ecran_inexistant(monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [])
    ok, detail = media_control.agir_sur_ecran(9, "pause")
    assert not ok
    assert "aucune fenêtre" in detail


def test_repli_clavier_quand_aucune_session(monkeypatch):
    """
    Beaucoup de lecteurs de sites de streaming n'exposent pas de session
    média : on doit alors afficher la fenêtre et envoyer la touche pause.
    """
    cible = fenetre("Anime-Sama - Firefox", "firefox.exe", 2, handle=42)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [cible])
    monkeypatch.setattr(media_control, "sessions", lambda: [])
    affichees = []
    monkeypatch.setattr(desktop, "mettre_au_premier_plan",
                        lambda h: affichees.append(h) or True)
    monkeypatch.setattr(media_control.win_utils, "press_key", lambda code: True)

    ok, detail = media_control.agir_sur_ecran(2, "pause")
    assert ok
    assert affichees == [42], "la fenêtre visée devait être mise au premier plan"
    assert "clavier" in detail
