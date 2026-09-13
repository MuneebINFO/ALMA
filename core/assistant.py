"""
L assistant : assemble configuration, stockage, routeur, voix et entrées.

C est le seul objet dont les commandes ont besoin ; il expose tout via le
CommandContext (config, storage, io, historique, confirmations).
"""

from __future__ import annotations

import logging
import time

from config import deriver_mots_appel, load_config
from core.context import SOURCE_TEXT, Response, Utterance
from core.registry import load_commands
from core.router import Router
from core.wake import MoteurEcoute
from core.scheduler import Scheduler
from core.storage import Storage
from core.preferences import CATALOGUE, Preferences
from core.tts import TextToSpeech

log = logging.getLogger(__name__)

AFFIRMATIONS = {"oui", "o", "yes", "y", "ok", "d accord", "daccord", "vas y", "confirme", "carrement"}
NEGATIONS = {"non", "n", "no", "annule", "stop", "laisse tomber"}


class Assistant:
    """Coeur de Alma : recoit une phrase, la route, renvoie une reponse."""

    def __init__(self, config=None, io=None, tts=None, stt=None) -> None:
        self.config = config if config is not None else load_config()
        self.storage = Storage(self.config)
        # Ce qu Alma a retenu de vous. Deja APPLIQUE a la configuration par
        # load_config ; le magasin sert a ecrire les changements suivants.
        self.preferences = Preferences(
            self.config.resolve_path("preferences", "data/preferences.json"))
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
        # Ecran de travail. Contrairement au reste du contexte, il N EXPIRE
        # PAS : une fois qu on a demande l ecran 2, tout s y passe jusqu a ce
        # qu on demande explicitement le contraire.
        self.ecran_actif = 1
        # Branche par l interface pour signaler visuellement un changement.
        self.signal_ecran = None
        # Branche par l interface : elle affiche le nom de l assistant, et
        # doit donc etre prevenue quand il change.
        self.signal_personnalisation = None
        # Poignee de la DERNIERE fenetre non-Alma que l utilisateur a eue
        # devant lui, et poignee de la fenetre d Alma elle-meme. L interface
        # les tient a jour (voir gui.py) : quand Alma est au premier plan --
        # mode vocal, plein ecran -- c est ce qui permet de savoir « la
        # fenetre ou j etais ».
        self.fenetre_utilisateur = 0
        self.poignee_alma = 0
        # Instant du dernier arret d action, pour savoir si « arrete » visait
        # cette action ou la session d ecoute.
        self._arret_a = -1e9
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

    # -- personnalisation -----------------------------------------------------
    def personnaliser(self, valeurs: dict) -> bool:
        """
        Applique des reglages MAINTENANT, et les retient pour la prochaine fois.

        Les deux moities comptent autant l une que l autre : sans la premiere,
        « appelle-toi Jarvis » ne repondrait au nouveau nom qu au prochain
        lancement ; sans la seconde, il l oublierait en se fermant.

        `valeurs` porte des chemins de configuration (« general.user_name »).
        Plusieurs a la fois quand un seul ordre en touche plusieurs : se
        renommer change le nom ET le mot d appel.
        """
        for chemin, valeur in valeurs.items():
            self.config.set(chemin, valeur)
        retenu = self.preferences.definir_plusieurs(valeurs)
        self._appliquer(set(valeurs))
        return retenu

    def oublier_personnalisations(self) -> int:
        """Efface les personnalisations et recharge la configuration d origine."""
        combien = self.preferences.tout_oublier()
        if combien:
            self.config.data = load_config(
                preferences_file=self.preferences.chemin).data
            self._appliquer({reglage.chemin for reglage in CATALOGUE})
        return combien

    def _appliquer(self, chemins: set) -> None:
        """
        Repercute un changement de reglage sur ce qui tourne deja.

        Chaque objet construit a partir de la configuration en garde une
        COPIE : le moteur d ecoute a son mot d appel, la synthese sa voix.
        Changer la configuration ne suffit donc pas, il faut les prevenir.
        """
        if chemins & {"general.assistant_name", "general.wake_word",
                      "general.wake_prefixes", "voice.armed_seconds",
                      "voice.sleep_words"}:
            deriver_mots_appel(self.config.data)
            self.moteur.reconfigurer(self.config)
        if chemins & {"voice.neural_voice", "voice.neural_rate", "voice.rate"}:
            try:
                self.tts.reconfigurer()
            except Exception as exc:          # pragma: no cover - defensif
                log.debug("Voix inchangée : %s", exc)
        if self.signal_personnalisation is not None:
            try:
                self.signal_personnalisation()
            except Exception as exc:          # pragma: no cover - defensif
                log.debug("Interface non prévenue : %s", exc)

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
        arrete = self.defilement.arreter()
        if arrete:
            self._arret_a = time.monotonic()
        return arrete

    def vient_d_interrompre(self, delai: float = 5.0) -> bool:
        """
        Une action vient-elle d etre arretee ?

        L interface arrete le defilement des qu elle ENTEND une voix, sans
        attendre de savoir ce qui a ete dit. Quand « arrete » arrive enfin
        transcrit, il n y a donc plus rien a arreter -- et sans cette
        memoire, le mot serait pris pour une fin de session.
        """
        return time.monotonic() - self._arret_a <= delai

    def interrompre_parole(self) -> bool:
        """
        Fait taire l assistant immediatement.

        Appele des que le micro DETECTE de la voix, sans attendre la
        transcription : sinon il finirait sa phrase pendant qu on lui parle,
        avec plusieurs secondes de retard.
        """
        try:
            return self.tts.arreter()
        except Exception:
            return False

    def definir_ecran(self, index: int) -> bool:
        """
        Choisit l ecran sur lequel travailler.

        Retourne True si l ecran a change. Le signal visuel n est envoye que
        dans ce cas : reconfirmer l ecran courant ne doit pas faire clignoter
        l ecran pour rien.
        """
        from core import desktop

        index = int(index)
        ecrans = desktop.ecrans()
        if ecrans and not 1 <= index <= len(ecrans):
            raise ValueError("écran " + str(index) + " inexistant")
        change = index != self.ecran_actif
        self.ecran_actif = index
        if self.signal_ecran is not None:
            try:
                self.signal_ecran(index)
            except Exception as exc:
                log.debug("Signal d écran impossible : %s", exc)
        return change

    def fenetre_courante(self):
        """
        La fenêtre sur laquelle l'utilisateur travaille, ou None.

        Celle au premier plan si ce n'est pas Alma ; sinon la dernière fenêtre
        non-Alma qu'il a eue devant lui, que l'interface garde en mémoire.
        C'est le repère de « cette fenêtre-ci » quand rien d'autre ne le dit.
        """
        from core import desktop

        devant = desktop.fenetre_au_premier_plan()
        if devant is not None and devant.handle != self.poignee_alma:
            return devant
        return desktop.fenetre_par_poignee(self.fenetre_utilisateur)

    def noter_fenetre_utilisateur(self, hwnd) -> None:
        """
        Appelé souvent par l'interface : retient la dernière fenêtre au
        premier plan qui n'était pas Alma. Volontairement sans coût -- une
        simple comparaison, pas d'énumération des fenêtres.
        """
        if hwnd and hwnd != self.poignee_alma:
            self.fenetre_utilisateur = hwnd

    def oublier_contexte(self) -> None:
        """Vide la memoire de court terme (fin de session)."""
        self.contexte.clear()

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
