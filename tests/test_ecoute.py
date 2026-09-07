"""
Tests de l'interruption de la parole.

Exigence : quand on parle à l'assistant pendant qu'il parle, il doit se taire
IMMÉDIATEMENT — pas finir sa phrase.
"""

import queue

import pytest

from core.tts import TextToSpeech


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
        interrompu = bool(self.texte_en_cours)
        self.arrets += 1
        self.texte_en_cours = ""
        return interrompu

    def wait(self, timeout=None):
        pass

    def list_voices(self):
        return []

    def shutdown(self):
        pass


def test_interrompre_la_parole_coupe_tout_de_suite(assistant):
    tts = TTSFactice()
    assistant.tts = tts
    tts.say("une phrase longue qu'il ne doit pas terminer")
    assert tts.parle() is True
    assert assistant.interrompre_parole() is True
    assert tts.parle() is False, "il doit se taire, pas finir sa phrase"


def test_interrompre_quand_il_se_tait_deja(assistant):
    assistant.tts = TTSFactice()
    assert assistant.interrompre_parole() is False


def test_la_coupure_a_lieu_des_la_detection_de_la_voix(assistant):
    """
    Le point décisif : la coupure est déclenchée par le NIVEAU SONORE, pas par
    la transcription. Attendre le texte, c'est attendre la fin de la phrase de
    l'utilisateur plus l'aller-retour réseau — plusieurs secondes pendant
    lesquelles l'assistant continuerait de parler.

    On rejoue ici la décision prise dans le rappel de niveau du micro.
    """
    tts = TTSFactice()
    assistant.tts = tts
    tts.say("je vais être interrompu")

    def sur_niveau(etat_audio):
        if etat_audio == "parole":
            assistant.interrompre_parole()

    sur_niveau("attente")
    assert tts.parle() is True, "le silence ne doit rien couper"
    sur_niveau("parole")
    assert tts.parle() is False
    assert tts.arrets == 1


def test_la_file_dattente_est_videe():
    """
    Couper doit aussi jeter ce qui restait à dire : sinon la phrase suivante
    démarrerait aussitôt et l'interruption n'aurait servi à rien.
    """
    tts = TextToSpeech.__new__(TextToSpeech)
    tts._queue = queue.Queue()
    tts.texte_en_cours = "en cours"
    tts._engine = None
    tts._available = True
    tts._queue.put(("phrase suivante", False))
    tts._queue.put(("encore une", False))

    assert tts.arreter() is True
    assert tts._queue.empty(), "la file doit être vidée"
    assert tts.texte_en_cours == ""


def test_l_interruption_ne_plante_pas_si_la_synthese_echoue(assistant):
    """Un moteur en panne ne doit pas empêcher d'écouter."""
    class TTSCasse(TTSFactice):
        def arreter(self):
            raise RuntimeError("moteur en panne")

    assistant.tts = TTSCasse()
    assert assistant.interrompre_parole() is False
