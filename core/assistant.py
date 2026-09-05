"""
L assistant : assemble configuration, stockage, routeur, voix et entrées.

C est le seul objet dont les commandes ont besoin ; il expose tout via le
CommandContext (config, storage, io, historique, confirmations).
"""

from __future__ import annotations

import logging

from config import load_config
from core.context import SOURCE_TEXT, Response, Utterance
from core.registry import load_commands
from core.router import Router
from core.scheduler import Scheduler
from core.storage import Storage
from core.tts import TextToSpeech

log = logging.getLogger(__name__)

AFFIRMATIONS = {"oui", "o", "yes", "y", "ok", "d accord", "daccord", "vas y", "confirme", "carrement"}
NEGATIONS = {"non", "n", "no", "annule", "stop", "laisse tomber"}


class Assistant:
    """Coeur de Alma : recoit une phrase, la route, renvoie une reponse."""

    def __init__(self, config=None, io=None, tts=None, stt=None) -> None:
        self.config = config if config is not None else load_config()
        self.storage = Storage(self.config)
        self.tts = tts if tts is not None else TextToSpeech(self.config)
        self.stt = stt
        self.router = Router()
        self.scheduler = Scheduler(self)
        self.running = True
        self.last_utterance: Utterance | None = None
        self.last_command_text: str = ""
        self.session_history: list = []

        load_commands()

        if io is None:
            from core.input_sources import TextInput

            io = TextInput()
        self.io = io

    # -- propriêtes -----------------------------------------------------------
    @property
    def name(self) -> str:
        return str(self.config.get("general.assistant_name", "Alma"))

    @property
    def speaks(self) -> bool:
        """La lecture a voix haute est-elle activé ?"""
        return bool(self.config.get("voice.speak_responses", True)) and self.tts.available

    # -- sorties --------------------------------------------------------------
    def emit(self, text: str, speak: bool = True) -> None:
        """Affiche (et eventuellement lit) un message."""
        if not text:
            return
        self.io.write(self.name + " > " + text)
        if speak and self.speaks:
            self.tts.say(text)

    def confirm(self, question: str) -> bool:
        """
        Demande une confirmation explicite. Utilise avant toute action
        destructrice (arret, redemarrage, suppression de notes...).
        """
        if not self.config.get("general.confirm_dangerous_actions", True):
            return True
        answer = self.io.ask(self.name + " > " + question + " (oui/non)")
        normalized = " ".join(str(answer or "").lower().replace("'", " ").split())
        return normalized in AFFIRMATIONS

    # -- traitement -----------------------------------------------------------
    def handle(self, text: str, source: str = SOURCE_TEXT) -> Response:
        """
        Traite une demande, quelle que soit sa provenance (texte, voix, geste).
        C est le point d entree unique : aucune logique metier ailleurs.
        """
        utterance = Utterance.parse(
            text, source=source, wake_words=self.config.get("general.wake_words")
        )
        if utterance.is_empty():
            return Response(text="", speak=False)

        self.last_utterance = utterance
        response, resolution = self.router.run(utterance, self)
        command_name = resolution.command.name if resolution else "inconnue"

        # On memorise pour "repete" (sans enregistrer "repete" lui-meme).
        if command_name not in ("repeat_last", "inconnue"):
            self.last_command_text = utterance.raw
        self.session_history.append((utterance.raw, command_name))
        try:
            self.storage.log_command(utterance.raw, command_name, source, response.text)
        except Exception as exc:
            log.debug("Historique non ecrit : %s", exc)

        if response.should_exit:
            self.running = False
        return response

    def handle_and_emit(self, text: str, source: str = SOURCE_TEXT) -> Response:
        """Traite une demande puis affiche/lit la reponse."""
        response = self.handle(text, source=source)
        if response.text:
            self.emit(response.text, speak=response.speak)
        return response

    # -- boucle principale ----------------------------------------------------
    def greet(self) -> None:
        from commands.smalltalk import greeting_for_now

        user = str(self.config.get("general.user_name", "") or "")
        hello = greeting_for_now(user)
        self.emit(hello + " Tapez « aide » pour voir ce que je sais faire.")

        # Rappels arrives pendant que Alma etait eteint.
        try:
            missed = self.scheduler.restore()
        except Exception as exc:
            log.debug("Restauration des rappels impossible : %s", exc)
            missed = []
        for item in missed:
            self.emit("Rappel manqué : " + str(item.get("label", "")))

    def run(self) -> None:
        """Boucle : lire une demande, la router, afficher la reponse."""
        self.greet()
        while self.running:
            try:
                text = self.io.read()
            except KeyboardInterrupt:
                self.emit("Interruption clavier. À bientôt.")
                break
            if not text or not text.strip():
                continue
            self.handle_and_emit(text, source=self.io.source)
        self.shutdown()

    def shutdown(self) -> None:
        """Arret propre : on laisse la synthese finir de parler."""
        try:
            self.scheduler.shutdown()
        except Exception:
            pass
        try:
            if self.tts.available:
                self.tts.wait()
                self.tts.shutdown()
        except Exception:
            pass
        try:
            self.io.close()
        except Exception:
            pass
