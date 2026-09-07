"""
Tests du contexte d'écran.

Règle : une fois qu'on a demandé un écran, tout s'y passe — et cela ne
s'efface pas avec la session, seulement sur demande explicite.
"""

import pytest

from core import desktop
from core.context import CommandContext, Utterance


def fenetre(titre, ecran, processus="chrome.exe", handle=1):
    return desktop.Fenetre(handle=handle, titre=titre, processus=processus, ecran=ecran)


@pytest.fixture
def deux_ecrans(monkeypatch):
    monkeypatch.setattr(desktop, "ecrans", lambda: [
        desktop.Ecran(1, (0, 0, 1920, 1200), 100),
        desktop.Ecran(2, (0, -1350, 2400, 0), 200),
    ])


# --------------------------------------------------------------------------
# Mémoire de l'écran
# --------------------------------------------------------------------------
def test_ecran_1_par_defaut(assistant):
    assert assistant.ecran_actif == 1


def test_changer_d_ecran(assistant, deux_ecrans):
    assert assistant.definir_ecran(2) is True
    assert assistant.ecran_actif == 2


def test_redemander_le_meme_ecran_ne_change_rien(assistant, deux_ecrans):
    assistant.definir_ecran(2)
    assert assistant.definir_ecran(2) is False, "aucun changement à signaler"


def test_l_ecran_ne_s_efface_pas_avec_le_contexte(assistant, deux_ecrans):
    """
    Le site en mémoire expire avec la session ; l'écran, non. Il ne change
    que sur demande explicite.
    """
    assistant.definir_ecran(2)
    assistant.memoriser("site", "youtube")
    assistant.oublier_contexte()
    assert assistant.rappeler("site") is None
    assert assistant.ecran_actif == 2, "l'écran doit survivre à la fin de session"


def test_un_ecran_inexistant_est_refuse(assistant, deux_ecrans):
    with pytest.raises(ValueError):
        assistant.definir_ecran(5)
    assert assistant.ecran_actif == 1, "l'écran courant reste inchangé"


# --------------------------------------------------------------------------
# Signal visuel
# --------------------------------------------------------------------------
def test_le_signal_est_emis_au_changement(assistant, deux_ecrans):
    signaux = []
    assistant.signal_ecran = signaux.append
    assistant.definir_ecran(2)
    assert signaux == [2]


def test_un_signal_defaillant_ne_bloque_pas(assistant, deux_ecrans):
    """L'assistant doit continuer même si l'animation échoue."""
    def casse(index):
        raise RuntimeError("pas d'affichage")

    assistant.signal_ecran = casse
    assert assistant.definir_ecran(2) is True
    assert assistant.ecran_actif == 2


# --------------------------------------------------------------------------
# Les commandes suivent l'écran choisi
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "va sur l'écran 2", "écran 2", "passe sur le deuxième écran",
    "bascule sur l'écran de droite", "mets toi sur l'écran 2",
])
def test_routage_du_choix_d_ecran(router, config, phrase):
    utterance = Utterance.parse(phrase, wake_words=config.get("general.wake_words"))
    resolution = router.resolve(utterance, None)
    assert resolution is not None and resolution.command.name == "choisir_ecran", phrase


@pytest.mark.parametrize("phrase,attendu", [
    ("mets pause sur l'écran 2", "media_pause_ecran"),
    ("reprends la lecture sur l'écran 2", "media_reprise_ecran"),
    ("arrête la vidéo sur le deuxième écran", "media_pause_ecran"),
    ("chanson suivante", "media_next"),
    ("passe à la chanson suivante", "media_next"),
])
def test_les_commandes_voisines_ne_sont_pas_capturees(router, config, phrase, attendu):
    """Le motif « écran » est large : il ne doit pas manger les commandes média."""
    utterance = Utterance.parse(phrase, wake_words=config.get("general.wake_words"))
    resolution = router.resolve(utterance, None)
    assert resolution is not None and resolution.command.name == attendu, phrase


def test_la_pause_sans_numero_vise_l_ecran_choisi(assistant, deux_ecrans, monkeypatch):
    """« Mets pause » après « va sur l'écran 2 » doit viser l'écran 2."""
    from core import media_control

    vises = []
    monkeypatch.setattr(media_control, "agir_sur_ecran",
                        lambda index, action: vises.append((index, action)) or (True, "ok"))
    assistant.definir_ecran(2)
    assistant.handle("mets pause sur l'écran")
    assert vises and vises[0][0] == 2


def test_les_fenetres_visees_sont_celles_de_l_ecran_choisi(assistant, deux_ecrans, monkeypatch):
    from commands.interaction import fenetre_visee

    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Page A - Chrome", ecran=1, handle=10),
        fenetre("Page B - Chrome", ecran=2, handle=20),
    ])
    assistant.oublier_contexte()
    utterance = Utterance.parse("scrolle", wake_words=assistant.config.get("general.wake_words"))
    ctx = CommandContext(utterance, assistant)

    assistant.definir_ecran(1)
    assert fenetre_visee(ctx).handle == 10
    assistant.definir_ecran(2)
    assert fenetre_visee(ctx).handle == 20


def test_une_fenetre_hors_ecran_reste_trouvable(assistant, deux_ecrans, monkeypatch):
    """
    L'écran est une préférence, pas une prison : si le site n'est ouvert que
    sur l'autre écran, mieux vaut l'y trouver que de répondre qu'il n'existe pas.
    """
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        fenetre("Netflix - Chrome", ecran=1, handle=10),
    ])
    assistant.definir_ecran(2)
    assert desktop.trouver_fenetre("netflix", ecran=2).handle == 10
