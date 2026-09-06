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
from core.wake import MoteurEcoute
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
        # Session d ecoute : partagee par le mode texte et le mode voix, pour
        # que les commandes puissent savoir si un echange est en cours.
        self.moteur = MoteurEcoute(self.config)
        # Memoire de court terme : le site ou l application dont on vient de
        # parler, afin que « recherche Damso » suive « va sur YouTube ».
        self.contexte: dict = {}
        # Defilement en cours, s il y en a un : il doit pouvoir etre
        # interrompu par la voix pendant qu il tourne.
        from core.interaction import Defilement

        self.defilement = Defilement()
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

    # -- memoire de court terme -----------------------------------------------
    @property
    def duree_contexte(self) -> float:
        """Duree de validite du contexte, alignee sur la session d ecoute."""
        return float(self.config.get("voice.armed_seconds", 60))

    def memoriser(self, cle: str, valeur) -> None:
        """Retient un element de contexte (le site en cours, par exemple)."""
        import time

        self.contexte[cle] = (valeur, time.monotonic())

    def rappeler(self, cle: str, defaut=None):
        """
        Relit un element de contexte, s il est encore recent.

        Le contexte expire avec la session : passe ce delai, « recherche X »
        redevient une recherche web ordinaire et non une recherche sur le
        dernier site visite.
        """
        import time

        entree = self.contexte.get(cle)
        if entree is None:
            return defaut
        valeur, pose_a = entree
        if time.monotonic() - pose_a > self.duree_contexte:
            del self.contexte[cle]
            return defaut
        return valeur

    def interrompre(self) -> bool:
        """
        Arrete l action en cours (defilement). Retourne True si quelque chose
        a bien ete interrompu : dire « arrete » pendant un defilement doit
        arreter le defilement, pas refermer la session d ecoute.
        """
        return self.defilement.arreter()

    def oublier_contexte(self) -> None:
        """Vide la memoire de court terme (fin de session)."""
        self.contexte.clear()

    # -- choix de la transcription --------------------------------------------
    def corriger(self, texte: str) -> str:
        """
        Applique les corrections de transcription connues, mot a mot.

        La reconnaissance bute sur les mots anglais dans une phrase francaise :
        « scroll » revient souvent en « Paul ». La table est dans la config
        (voice.corrections), donc completable sans toucher au code.
        """
        from core import text_utils

        corrections = self.config.get("voice.corrections", {}) or {}
        if not corrections:
            return texte
        table = {
            text_utils.normalize(str(faux)).strip(): str(vrai)
            for faux, vrai in corrections.items()
        }
        mots = texte.split()
        corriges = [
            table.get(text_utils.normalize(mot).strip(" .,!?"), mot) for mot in mots
        ]
        return " ".join(corriges)

    def choisir_transcription(self, propositions) -> str:
        """
        Choisit, parmi les hypotheses du moteur, celle qui a du sens.

        Le moteur classe ses hypotheses par probabilite acoustique, sans
        savoir ce que l assistant sait faire. On retient donc la premiere qui
        correspond a une commande connue -- ou a une correction connue --
        plutot que la premiere tout court. A defaut, on garde son classement.
        """
        from core.context import SOURCE_VOICE, Utterance

        if isinstance(propositions, str):
            propositions = [propositions]
        propositions = [p for p in propositions if p and p.strip()]
        if not propositions:
            return ""

        wake_words = self.config.get("general.wake_words")
        for brute in propositions:
            for candidate in (brute, self.corriger(brute)):
                appel, reste = self.moteur.separer_mot_appel(candidate)
                if appel and not reste.strip():
                    return candidate            # le nom seul suffit
                phrase = reste if appel else candidate
                if not phrase.strip():
                    continue
                utterance = Utterance.parse(phrase, source=SOURCE_VOICE, wake_words=wake_words)
                if self.router.resolve(utterance, self) is not None:
                    return candidate
        return propositions[0]

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
            self.defilement.arreter()
        except Exception:
            pass
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
