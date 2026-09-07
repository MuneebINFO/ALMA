"""
Tests de l'interruption de la parole.

Exigence : quand on parle à l'assistant pendant qu'il parle, il doit se taire
IMMÉDIATEMENT — pas finir sa phrase.
"""

import queue
import threading
import time

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
    tts._interrompre = threading.Event()
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


# --------------------------------------------------------------------------
# La lecture audio doit pouvoir etre coupee par un AUTRE thread
# --------------------------------------------------------------------------
def test_la_lecture_audio_sarrete_quand_un_autre_thread_la_coupe(monkeypatch, tmp_path):
    """
    Le bug : « play ... wait » monopolisait le périphérique MCI, si bien que
    le « stop » envoyé par le thread d'écoute restait en file jusqu'à la fin
    du fichier. ALMA finissait sa phrase malgré l'interruption.
    """
    from core import voice_neural

    commandes = []
    monkeypatch.setattr(voice_neural, "_mci",
                        lambda c: commandes.append(c) or 0)
    # Le périphérique se dit « en lecture » indéfiniment : seule une coupure
    # peut faire sortir la boucle de surveillance.
    monkeypatch.setattr(voice_neural, "_mci_texte", lambda c: "playing")
    monkeypatch.setattr(voice_neural, "INTERVALLE_SURVEILLANCE", 0.005)

    fichier = tmp_path / "voix.mp3"
    fichier.write_bytes(b"0")

    fini = threading.Event()
    threading.Thread(
        target=lambda: (voice_neural.jouer_fichier(fichier), fini.set()),
        daemon=True,
    ).start()

    debut = time.time()
    while voice_neural._alias_courant is None and time.time() - debut < 5:
        time.sleep(0.005)
    assert voice_neural._alias_courant, "la lecture n'a pas démarré"

    assert voice_neural.arreter_lecture() is True
    assert fini.wait(timeout=5), "la lecture ne s'est pas arrêtée"
    assert any(c.startswith("play ") and not c.endswith(" wait") for c in commandes),         "la lecture doit être lancée sans « wait », sinon rien ne peut la couper"


def test_aucune_lecture_a_couper():
    from core import voice_neural

    voice_neural._alias_courant = None
    assert voice_neural.arreter_lecture() is False


# --------------------------------------------------------------------------
# Repli SAPI5 : interruptible entre deux phrases
# --------------------------------------------------------------------------
def test_le_texte_est_decoupe_en_phrases():
    from core.tts import decouper

    assert decouper(
        "Bonjour. Comment allez-vous aujourd'hui ? Il fait beau et je vais bien."
    ) == [
        "Bonjour. Comment allez-vous aujourd'hui ?", "Il fait beau et je vais bien.",
    ]
    # Une réplique courte reste d'un seul tenant : la hacher n'apporterait rien.
    assert decouper("Oui ?") == ["Oui ?"]
    assert decouper("") == [""]


def test_arreter_leve_le_drapeau_lu_par_le_thread_de_lecture():
    """
    SAPI5 ne peut pas être arrêté depuis un autre thread : c'est le thread de
    lecture qui doit constater l'interruption entre deux phrases.
    """
    tts = TextToSpeech.__new__(TextToSpeech)
    tts._queue = queue.Queue()
    tts._interrompre = threading.Event()
    tts.texte_en_cours = "en cours"
    tts._engine = None
    tts._available = True

    tts.arreter()
    assert tts._interrompre.is_set()
