"""
Synthese vocale (Text To Speech), avec deux moteurs :

  1. VOIX NEURONALE (edge-tts) -- par defaut : voix feminine francaise
     nettement plus humaine. Gratuite, sans cle API, mais necessite internet.
  2. SAPI5 local (pyttsx3) -- repli automatique : 100% hors ligne, plus
     robotique, utilise si le reseau ou edge-tts manque.

IMPORTANT (bug corrige) : sous Windows, SAPI passe par COM et un moteur
pyttsx3 cree dans un thread ne peut PAS etre pilote depuis un autre thread --
runAndWait() s y fige indefiniment. Le thread de lecture cree donc lui-meme
son moteur et reste le seul a y toucher.
"""

from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger(__name__)

INIT_TIMEOUT = 12.0

# Repliques courtes pre-synthetisees au demarrage, pour une reponse instantanee.
PHRASES_PRECHAUFFEES = (
    "Oui ?",
    "Je vous écoute.",
    "À votre service.",
    "Oui, je suis là.",
)


class TextToSpeech:
    """Synthese vocale non bloquante : le moteur vit dans son propre thread."""

    def __init__(self, config=None) -> None:
        self.config = config
        self.voices: list = []
        self.error = ""
        self.moteur_actif = "aucun"       # "neuronal" | "sapi5" | "aucun"
        self._neuronale = None
        self._queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._available = False
        self._stop = threading.Event()
        # Texte en cours de lecture : sert a reconnaitre notre propre voix si
        # le micro la capte, et a savoir si l on peut etre interrompu.
        self.texte_en_cours = ""
        self._engine = None
        self._thread = threading.Thread(target=self._worker, daemon=True, name="alma-tts")
        self._thread.start()
        self._ready.wait(INIT_TIMEOUT)

    @property
    def available(self) -> bool:
        self._ready.wait(INIT_TIMEOUT)
        return self._available

    # -- reglages -------------------------------------------------------------
    def _reglage(self, chemin: str, defaut):
        return self.config.get(chemin, defaut) if self.config else defaut

    def _init_neuronale(self) -> None:
        """Prepare la voix neuronale si elle est demandee et disponible."""
        moteur = str(self._reglage("voice.engine", "auto") or "auto").lower()
        if moteur == "sapi5":
            return
        from core.voice_neural import VOIX_PAR_DEFAUT, VoixNeuronale

        voix = str(self._reglage("voice.neural_voice", VOIX_PAR_DEFAUT) or VOIX_PAR_DEFAUT)
        vitesse = str(self._reglage("voice.neural_rate", "+0%") or "+0%")
        candidate = VoixNeuronale(voix=voix, vitesse=vitesse)
        if not candidate.disponible:
            self.error = candidate.erreur
            return
        # Le prechauffage valide aussi l acces reseau : s il echoue, on saura
        # tout de suite qu il faut basculer sur SAPI5.
        if candidate.prechauffer(PHRASES_PRECHAUFFEES) == 0:
            self.error = "Voix neuronale injoignable (hors ligne ?) : repli sur la voix locale."
            return
        self._neuronale = candidate
        self.moteur_actif = "neuronal"
        self._available = True

    # -- thread de lecture ----------------------------------------------------
    def _worker(self) -> None:
        """Cree les moteurs PUIS les pilote : tout se passe dans ce seul thread."""
        engine = None
        com_initialise = False
        try:
            try:
                import pythoncom

                pythoncom.CoInitialize()
                com_initialise = True
            except Exception:
                pass

            try:
                self._init_neuronale()
            except Exception as exc:
                log.debug("Voix neuronale indisponible : %s", exc)

            engine = self._init_sapi5()
            self._engine = engine
            if engine is not None and self.moteur_actif == "aucun":
                self.moteur_actif = "sapi5"
            if engine is not None:
                self._available = True
            if not self._available and not self.error:
                self.error = "Aucun moteur de synthèse vocale disponible."
        finally:
            self._ready.set()

        while not self._stop.is_set():
            try:
                element = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if element is None:
                self._queue.task_done()
                break
            texte, cacher = element
            self.texte_en_cours = texte
            try:
                joue = False
                if self._neuronale is not None:
                    joue = self._neuronale.dire(texte, cacher=cacher)
                if not joue and engine is not None:
                    engine.say(texte)
                    engine.runAndWait()
            except Exception as exc:
                log.debug("Echec de lecture : %s", exc)
            finally:
                self.texte_en_cours = ""
                self._queue.task_done()

        for fermeture in (
            lambda: engine.stop() if engine is not None else None,
            lambda: self._neuronale.nettoyer() if self._neuronale is not None else None,
        ):
            try:
                fermeture()
            except Exception:
                pass
        if com_initialise:
            try:
                import pythoncom

                pythoncom.CoUninitialize()
            except Exception:
                pass

    def _init_sapi5(self):
        """Prepare le moteur local SAPI5 (repli hors ligne)."""
        try:
            import pyttsx3
        except ImportError:
            if not self.error:
                self.error = "pyttsx3 n'est pas installé (pip install -r requirements-voice.txt)."
            return None
        try:
            engine = pyttsx3.init()
        except Exception as exc:
            log.warning("Initialisation SAPI5 impossible : %s", exc)
            return None

        try:
            engine.setProperty("rate", int(self._reglage("voice.rate", 175)))
            engine.setProperty("volume", float(self._reglage("voice.volume", 1.0)))
        except Exception:
            pass
        try:
            self.voices = [(v.id, v.name) for v in engine.getProperty("voices")]
        except Exception:
            self.voices = []

        voice_id = self._reglage("voice.voice_id", "")
        if voice_id:
            try:
                engine.setProperty("voice", voice_id)
            except Exception:
                log.warning("Voix « %s » introuvable : voix par défaut utilisée.", voice_id)
        else:
            self._choisir_voix_feminine(engine)
        return engine

    def _choisir_voix_feminine(self, engine) -> None:
        """
        Choisit une voix francaise, en preferant une voix feminine.
        Sous Windows francais, Hortense est la seule voix FR installee par
        defaut : elle sert de repli quand la voix neuronale est injoignable.
        """
        try:
            voix = list(engine.getProperty("voices"))
        except Exception:
            return

        def profil(v):
            blob = " ".join(
                filter(None, [getattr(v, "id", ""), getattr(v, "name", "")])
            ).lower()
            langues = " ".join(str(x) for x in (getattr(v, "languages", []) or [])).lower()
            francaise = "fr" in blob or "fr" in langues or "french" in blob
            feminine = any(
                mot in blob for mot in ("hortense", "julie", "female", "zira", "eva")
            ) or getattr(v, "gender", "") == "VoiceGenderFemale"
            return francaise, feminine

        # Priorite : francaise ET feminine > francaise > feminine.
        for critere in (
            lambda v: all(profil(v)),
            lambda v: profil(v)[0],
            lambda v: profil(v)[1],
        ):
            for v in voix:
                if critere(v):
                    try:
                        engine.setProperty("voice", v.id)
                    except Exception:
                        pass
                    return

    # -- API publique ---------------------------------------------------------
    def say(self, text: str, blocking: bool = False, cacher: bool = False) -> None:
        """
        Met un texte dans la file de lecture.
        `cacher` : conserve l audio pour un rejeu instantane (repliques courtes).
        """
        if not self.available or not text:
            return
        self._queue.put((text, cacher))
        if blocking:
            self.wait()

    def wait(self, timeout: float | None = None) -> None:
        """Attend la fin des lectures en cours."""
        if self._available:
            self._queue.join()

    def parle(self) -> bool:
        """True si une lecture est en cours ou en attente."""
        return bool(self.texte_en_cours) or not self._queue.empty()

    def arreter(self) -> bool:
        """
        Coupe la parole immediatement et vide la file d attente.

        Quand on lui parle, l assistant doit se taire et ecouter, pas finir
        sa phrase.
        """
        interrompu = bool(self.texte_en_cours)
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                interrompu = True
            except queue.Empty:
                break
        try:
            from core import voice_neural

            if voice_neural.arreter_lecture():
                interrompu = True
        except Exception:
            pass
        try:
            if self._engine is not None:
                self._engine.stop()
        except Exception:
            pass
        self.texte_en_cours = ""
        return interrompu

    def list_voices(self) -> list:
        """Voix SAPI5 installees (la voix neuronale, elle, se choisit par nom)."""
        self._ready.wait(INIT_TIMEOUT)
        return list(self.voices)

    def shutdown(self) -> None:
        """Arrete proprement le thread de lecture."""
        if not self._thread.is_alive():
            return
        self._stop.set()
        self._queue.put(None)
        self._thread.join(timeout=8)
