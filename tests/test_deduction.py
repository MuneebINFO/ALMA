"""
Tests de la déduction : retrouver l'intention malgré une transcription ratée.
"""

import pytest

from core import deduction
from core.context import Utterance


@pytest.fixture
def resout(assistant):
    """Prédicat « cette phrase correspond-elle à une commande ? »."""
    def _resout(phrase):
        essai = Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words"))
        return not essai.is_empty() and assistant.router.resolve(essai, assistant) is not None
    return _resout


# --------------------------------------------------------------------------
# Clé phonétique
# --------------------------------------------------------------------------
@pytest.mark.parametrize("a,b", [
    ("scroll", "scrolle"), ("scroll", "skroll"), ("pause", "pose"),
    ("clique", "clic"), ("video", "vidéos"),
])
def test_les_variantes_sonnent_pareil(a, b):
    assert deduction.se_ressemblent(a, b)


@pytest.mark.parametrize("a,b", [
    ("scroll", "paul"), ("volume", "video"), ("note", "musique"),
])
def test_les_mots_differents_ne_sont_pas_confondus(a, b):
    """La phonétique ne doit pas tout rapprocher, sinon elle ne sert à rien."""
    assert not deduction.se_ressemblent(a, b)


# --------------------------------------------------------------------------
# Déduction proprement dite
# --------------------------------------------------------------------------
# Uniquement des phrases que le routeur ne comprend PAS telles quelles :
# celles qu'il comprend déjà ne doivent pas être réécrites (test plus bas).
@pytest.mark.parametrize("entendu,attendu_contient", [
    ("Paul vers le bas", "bas"),          # le cas signalé : « scroll » mal entendu
    ("pol vers le bas", "bas"),
    ("roll vers le bas", "bas"),
    ("school vers le haut", "haut"),
    ("descendre un peu", "bas"),
    ("vers le haut", "haut"),
    ("pose", "pause"),
])
def test_l_intention_est_reconstruite(resout, entendu, attendu_contient):
    deduit = deduction.deduire(entendu, resout)
    assert deduit is not None, "rien déduit pour : " + entendu
    assert attendu_contient in deduit.lower()


def test_une_phrase_deja_comprise_nest_jamais_reecrite(resout):
    """
    Garde-fou essentiel : sans lui, « cherche Paul sur YouTube » deviendrait
    « cherche scroll sur YouTube ».
    """
    assert deduction.deduire("cherche Paul sur YouTube", resout) is None
    assert deduction.deduire("ouvre Chrome", resout) is None


def test_rien_nest_invente(resout):
    """Une phrase sans rapport ne doit produire aucune déduction."""
    for phrase in ("xyzzy plover blorb", "il fait beau aujourd hui", ""):
        assert deduction.deduire(phrase, resout) is None, phrase


def test_une_deduction_est_toujours_validee(assistant):
    """
    Rien n'est renvoyé qui ne corresponde à une commande : le prédicat de
    validation est la seule porte de sortie.
    """
    assert deduction.deduire("Paul vers le bas", lambda phrase: False) is None


# --------------------------------------------------------------------------
# De bout en bout, à travers l'assistant
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,mot_attendu", [
    ("pose", None),                    # déduit : « pause »
    ("plus fort", "volume"),           # compris directement
    ("quelle heure", "heures"),        # compris directement
    ("fais moi rire", None),           # compris directement
])
def test_l_assistant_execute_la_demande_deduite(assistant, phrase, mot_attendu,
                                                monkeypatch):
    # « pause » ne fait quelque chose que s il y a un lecteur sur l ecran de
    # travail : on en simule un, sinon le test mesurerait la machine de test
    # plutot que la deduction.
    from core import desktop, media_control

    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=1, titre="Une vidéo - YouTube - Google Chrome",
                        processus="chrome.exe", ecran=1),
    ])
    monkeypatch.setattr(media_control, "sessions", lambda: [
        media_control.SessionMedia("Chrome", "Une vidéo", media_control.EN_LECTURE),
    ])
    monkeypatch.setattr(media_control, "_agir_sur_session", lambda app, action: True)

    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " -> " + reponse.text
    if mot_attendu:
        assert mot_attendu in reponse.text.lower()


def test_l_assistant_renonce_proprement(assistant):
    from core.ai_fallback import SUGGESTIONS

    reponse = assistant.handle("xyzzy plover blorb")
    assert not reponse.ok
    assert reponse.text in SUGGESTIONS
