"""
Tests de la compréhension de la parole et de l'interruption.

Trois exigences : choisir la bonne hypothèse de transcription, pouvoir couper
la parole à l'assistant, et agir sans commenter.
"""

import pytest

from core import text_utils


# --------------------------------------------------------------------------
# Choix parmi les hypothèses du moteur
# --------------------------------------------------------------------------
def test_l_hypothese_qui_correspond_a_une_commande_est_retenue(assistant):
    """
    Le moteur classe par probabilité acoustique, sans savoir ce que
    l'assistant sait faire : « Paul » passe avant « scroll ».
    """
    assert assistant.choisir_transcription(["Paul", "scroll"]) == "scroll"


def test_une_correction_connue_est_appliquee(assistant):
    """Quand le moteur ne propose rien d'exploitable, la table corrige."""
    assert assistant.choisir_transcription(["Paul"]) == "scroll"
    assert assistant.choisir_transcription(["pose"]) == "pause"


def test_une_correction_ne_casse_pas_une_requete_legitime(assistant):
    """
    « Paul » est un mot valable dans une recherche : la correction ne doit
    s'appliquer que si l'original ne veut rien dire pour l'assistant.
    """
    phrase = "cherche Paul sur YouTube"
    assert assistant.choisir_transcription([phrase]) == phrase


def test_l_ordre_du_moteur_est_conserve_a_defaut(assistant):
    """Si rien ne correspond, on garde le classement du moteur."""
    propositions = ["blablabla incompréhensible", "autre chose"]
    assert assistant.choisir_transcription(propositions) == propositions[0]


def test_le_nom_seul_est_reconnu(assistant):
    assert assistant.choisir_transcription(["Alma"]) == "Alma"


def test_liste_vide(assistant):
    assert assistant.choisir_transcription([]) == ""
    assert assistant.choisir_transcription(["", "  "]) == ""


def test_la_correction_est_configurable(assistant):
    """La table vit dans config.yaml : complétable sans toucher au code."""
    assistant.config.set("voice.corrections", {"machin": "scroll"})
    assert assistant.corriger("machin") == "scroll"
    assistant.config.set("voice.corrections", {})
    assert assistant.corriger("machin") == "machin"


# --------------------------------------------------------------------------
# Couper la parole
# --------------------------------------------------------------------------
class TTSFactice:
    """Double de la synthèse vocale, pour observer les interruptions."""

    available = True
    voices: list = []
    error = ""

    def __init__(self):
        self.texte_en_cours = ""
        self.arrets = 0
        self.dits = []

    def say(self, text, blocking=False, cacher=False):
        self.dits.append(text)
        self.texte_en_cours = text

    def parle(self):
        return bool(self.texte_en_cours)

    def arreter(self):
        self.arrets += 1
        interrompu = bool(self.texte_en_cours)
        self.texte_en_cours = ""
        return interrompu

    def wait(self, timeout=None):
        pass

    def list_voices(self):
        return []

    def shutdown(self):
        pass


def test_la_parole_peut_etre_coupee():
    tts = TTSFactice()
    tts.say("une phrase longue que je vais couper")
    assert tts.parle() is True
    assert tts.arreter() is True
    assert tts.parle() is False
    assert tts.arreter() is False


def test_l_echo_de_sa_propre_voix_est_ignore():
    """
    Sans ce garde-fou, l'assistant s'interromprait lui-même dès qu'il parle
    dans des haut-parleurs.
    """
    en_cours = "Je fais défiler vers le bas"
    entendu = ["je fais défiler vers le bas"]

    norme = text_utils.normalize(en_cours)
    mots = [m for m in text_utils.tokenize(text_utils.normalize(entendu[0])) if len(m) >= 4]
    communs = sum(1 for m in mots if m in norme)
    assert communs / len(mots) >= 0.6, "cette phrase devrait être vue comme un écho"


def test_une_vraie_demande_nest_pas_prise_pour_un_echo():
    en_cours = "Je fais défiler vers le bas"
    mots = [m for m in text_utils.tokenize(text_utils.normalize("arrête")) if len(m) >= 4]
    norme = text_utils.normalize(en_cours)
    communs = sum(1 for m in mots if m in norme)
    assert communs / max(1, len(mots)) < 0.6


# --------------------------------------------------------------------------
# Agir sans commenter
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "scrolle",
    "fais défiler vers le haut",
])
def test_les_actions_ne_sont_pas_commentees(assistant, monkeypatch, phrase):
    """
    Une action dont l'effet est visible ne doit pas être annoncée : commenter
    « je fais défiler » pendant qu'on défile retarde l'exécution pour rien.
    """
    from core import desktop, interaction

    monkeypatch.setattr(interaction, "_molette", lambda n: None)
    monkeypatch.setattr(interaction, "position_souris", lambda: (0, 0))
    monkeypatch.setattr(interaction, "deplacer_souris", lambda x, y: None)
    monkeypatch.setattr(interaction, "_rectangle_fenetre", lambda h: (0, 0, 800, 600))
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=1, titre="Page - Chrome", processus="chrome.exe", ecran=1)
    ])

    reponse = assistant.handle(phrase)
    try:
        assert reponse.ok
        assert reponse.speak is False, "cette action ne doit pas être lue à voix haute"
        assert reponse.text, "elle doit tout de même apparaître dans le journal"
    finally:
        assistant.defilement.arreter()


def test_les_informations_restent_dites(assistant):
    """En revanche, une information sans effet visible doit être énoncée."""
    reponse = assistant.handle("quelle heure est-il")
    assert reponse.ok and reponse.speak is True
