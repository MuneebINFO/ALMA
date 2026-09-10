"""
Le lecteur visé est celui que l'utilisateur a SOUS LES YEUX.

Bug signalé : après avoir mis YouTube en pause puis être allé sur Prime Video,
« lance la vidéo » relançait YouTube — un lecteur d'arrière-plan — au lieu du
lecteur qu'on regardait. « pause » / « lance la vidéo » doivent viser la
fenêtre courante, jamais une session laissée en pause dans un autre onglet.
"""

import pytest

from core import desktop, media_control, win_utils


def fenetre(titre, processus, ecran, handle):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


def session(app, joue, titre="un contenu"):
    return media_control.SessionMedia(
        app, titre, media_control.EN_LECTURE if joue else media_control.EN_PAUSE
    )


@pytest.fixture
def machine(monkeypatch):
    """
    Écran 1 : deux Chrome — YouTube (en pause, propriétaire de la session) et
    Prime Video (aucune session). Chrome n'expose qu'une session : c'est le
    titre qui dit à quelle fenêtre elle appartient.
    """
    youtube = fenetre("Une vidéo - YouTube - Google Chrome", "chrome.exe", 1, 10)
    prime = fenetre("Le Seigneur des Anneaux - Prime Video - Google Chrome",
                    "chrome.exe", 1, 11)
    spotify = fenetre("Spotify Premium", "spotify.exe", 1, 12)

    etat = {
        "sessions": [session("Chrome", False, "Une vidéo")],
        "fenetres": [youtube, prime, spotify],
        "actions": [],
        "touches": [],
        "premier_plan": [],
    }
    monkeypatch.setattr(media_control, "sessions", lambda: list(etat["sessions"]))
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: list(etat["fenetres"]))
    monkeypatch.setattr(media_control, "_agir_sur_session",
                        lambda app, action: etat["actions"].append((app, action)) or True)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan",
                        lambda h: etat["premier_plan"].append(h) or True)
    monkeypatch.setattr(win_utils, "press_key",
                        lambda vk: etat["touches"].append(vk) or True)
    etat["youtube"], etat["prime"], etat["spotify"] = youtube, prime, spotify
    return etat


def regarder(assistant, fen):
    assistant.fenetre_courante = lambda: fen


def test_lance_la_video_ne_relance_pas_youtube_en_arriere_plan(assistant, machine):
    assistant.ecran_actif = 1
    regarder(assistant, machine["prime"])

    reponse = assistant.handle("lance la vidéo")

    assert ("Chrome", "play") not in machine["actions"], \
        "la session YouTube d'arrière-plan ne doit pas être relancée"
    # À défaut de session, on agit au clavier sur la fenêtre Prime Video.
    assert machine["premier_plan"] == [machine["prime"].handle]
    assert machine["touches"] == [media_control.VK_ESPACE]
    assert reponse.ok, reponse.text


def test_pause_vise_la_fenetre_regardee_et_pas_une_autre(assistant, machine):
    machine["sessions"] = [session("Chrome", True, "Une vidéo")]
    assistant.ecran_actif = 1
    regarder(assistant, machine["youtube"])

    reponse = assistant.handle("mets pause à la vidéo")

    assert ("Chrome", "pause") in machine["actions"]
    assert reponse.ok, reponse.text


def test_lance_la_video_relance_le_lecteur_regarde_s_il_a_la_session(assistant, machine):
    # YouTube est en pause ET c'est lui qu'on regarde : on le relance.
    assistant.ecran_actif = 1
    regarder(assistant, machine["youtube"])

    reponse = assistant.handle("lance la vidéo")

    assert ("Chrome", "play") in machine["actions"]
    assert machine["touches"] == [], "pas de repli clavier quand la session suffit"
    assert reponse.ok, reponse.text


def test_lecteur_dedie_garde_sa_session_meme_sans_titre_parlant(assistant, machine):
    machine["sessions"] = [session("Spotify", False, "un morceau")]
    assistant.ecran_actif = 1
    regarder(assistant, machine["spotify"])

    reponse = assistant.handle("reprends la lecture")

    assert ("Spotify", "play") in machine["actions"]
    assert reponse.ok, reponse.text


def test_sans_fenetre_connue_on_retombe_sur_le_raisonnement_par_ecran(assistant, machine):
    """Mode texte, aucune interface : le comportement historique est conservé."""
    machine["sessions"] = [session("Chrome", False, "Une vidéo")]
    assistant.ecran_actif = 1
    assistant.fenetre_courante = lambda: None

    reponse = assistant.handle("lance la vidéo")

    assert ("Chrome", "play") in machine["actions"]
    assert reponse.ok, reponse.text


def test_fenetre_regardee_sur_un_autre_ecran_est_ignoree(assistant, machine):
    """On travaille sur l'écran 1 ; la fenêtre au premier plan est sur l'écran 2."""
    ailleurs = fenetre("Netflix - Google Chrome", "chrome.exe", 2, 20)
    machine["fenetres"].append(ailleurs)
    machine["sessions"] = [session("Chrome", False, "Une vidéo")]
    assistant.ecran_actif = 1
    regarder(assistant, ailleurs)

    reponse = assistant.handle("lance la vidéo")

    # La fenêtre de l'écran 2 est écartée -> raisonnement par écran 1, qui
    # relance la session (rattachée à YouTube via son titre).
    assert ("Chrome", "play") in machine["actions"]
    assert reponse.ok, reponse.text
