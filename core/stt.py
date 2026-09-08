"""
Reconnaissance vocale (Speech To Text).

Deux moteurs, tous deux gratuits :
  - "google"  : API web gratuite de SpeechRecognition (aucune cle requise,
                mais necessite une connexion internet) ;
  - "vosk"    : 100% hors ligne, necessite de telecharger un modele Vosk.

Si les dependances audio ne sont pas installees, l objet reste utilisable :
`available` vaut False et l'assistant bascule automatiquement en mode texte.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)


class SpeechToText:
    """Wrapper autour de speech_recognition, avec repli hors ligne via Vosk."""

    def __init__(self, config=None) -> None:
        self.config = config
        self.available = False
        self.error = ""
        self._recognizer = None
        self._microphone = None
        self._vosk_model = None
        self._meter = None        # compteur de niveau, cree a la demande
        self.engine = str((config.get("voice.stt_engine") if config else "google") or "google")
        self.language = str((config.get("voice.stt_language") if config else "fr-FR") or "fr-FR")
        self._init()

    def _init(self) -> None:
        try:
            import speech_recognition as sr
        except ImportError:
            self.error = "Le module speech_recognition n'est pas installé (pip install -r requirements-voice.txt)."
            return
        try:
            self._recognizer = sr.Recognizer()
            if self.config:
                self._recognizer.energy_threshold = int(self.config.get("voice.energy_threshold", 300))
                self._recognizer.pause_threshold = float(self.config.get("voice.pause_threshold", 0.8))
            self._recognizer.dynamic_energy_threshold = True
            self._microphone = sr.Microphone()
            self.available = True
        except Exception as exc:
            self.error = "Microphone indisponible : " + str(exc)
            log.warning(self.error)
            return
        if self.engine == "vosk":
            self._init_vosk()

    def _init_vosk(self) -> None:
        """Charge un modele Vosk pour la reconnaissance hors ligne."""
        path = str(self.config.get("voice.vosk_model_path", "") if self.config else "")
        if not path:
            self.error = "voice.vosk_model_path non renseigne : repli sur le moteur Google."
            self.engine = "google"
            return
        try:
            from vosk import Model

            self._vosk_model = Model(path)
        except Exception as exc:
            self.error = "Modele Vosk illisible (" + str(exc) + ") : repli sur le moteur Google."
            self.engine = "google"

    def calibrate(self, duration: float = 1.0) -> None:
        """Mesure le bruit ambiant pour ajuster le seuil de detection."""
        if not self.available:
            return
        try:
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=duration)
        except Exception as exc:
            log.debug("Calibration impossible : %s", exc)

    def listen(self, timeout: float | None = None, phrase_time_limit: float | None = None) -> str:
        """
        Ecoûte le micro et retourne le texte reconnu (chaine vide si echec).
        Ne leve jamais d exception : le mode voix ne doit pas casser la boucle.
        """
        if not self.available:
            return ""
        import speech_recognition as sr

        timeout = timeout if timeout is not None else float(self.config.get("voice.timeout", 6) if self.config else 6)
        limit = phrase_time_limit if phrase_time_limit is not None else float(
            self.config.get("voice.phrase_time_limit", 12) if self.config else 12
        )
        try:
            with self._microphone as source:
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=limit)
        except sr.WaitTimeoutError:
            return ""
        except Exception as exc:
            log.debug("Echec de capture audio : %s", exc)
            return ""
        return self._transcribe(audio)

    def _compteur(self) -> "LevelMeterListener":
        """Compteur de niveau, cree a la demande avec les seuils configures."""
        if self._meter is None:
            self._meter = LevelMeterListener(
                plancher=self.config.get("voice.min_threshold") if self.config else None,
                facteur=self.config.get("voice.noise_factor") if self.config else None,
            )
        return self._meter

    def listen_live(self, on_level=None, timeout: float = 8.0,
                    phrase_limit: float = 12.0, doit_continuer=None) -> str:
        """
        Comme listen(), mais en remontant le NIVEAU SONORE en direct via
        `on_level(niveau, etat)`. Utilise par l interface graphique pour
        montrer que la voix est bien detectee pendant que l on parle.

        `doit_continuer()` permet d interrompre l ecoute proprement.
        """
        if not self.available:
            return ""
        import speech_recognition as sr

        compteur = self._compteur()
        if compteur.ambient == 0.0 and compteur.threshold == compteur.plancher:
            compteur.calibrate(0.8, on_level=on_level)

        brut = compteur.listen(
            on_level=on_level, timeout=timeout,
            phrase_limit=phrase_limit, doit_continuer=doit_continuer,
        )
        if not brut:
            return ""
        audio = sr.AudioData(brut, SAMPLE_RATE, SAMPLE_WIDTH)
        return self._transcribe(audio)

    def recalibrate(self, duration: float = 1.0, on_level=None) -> float:
        """Remesure le bruit ambiant (utile si l environnement change)."""
        return self._compteur().calibrate(duration, on_level=on_level)

    def fermer(self) -> None:
        """Libere le micro. Le flux est garde ouvert tant qu on ecoute."""
        if self._meter is not None:
            self._meter.fermer()

    def _transcribe(self, audio) -> str:
        import speech_recognition as sr

        if self.engine == "vosk" and self._vosk_model is not None:
            try:
                from vosk import KaldiRecognizer

                rec = KaldiRecognizer(self._vosk_model, 16000)
                rec.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
                return str(json.loads(rec.FinalResult()).get("text", "")).strip()
            except Exception as exc:
                log.debug("Echec Vosk : %s", exc)
                return ""
        try:
            return str(self._recognizer.recognize_google(audio, language=self.language)).strip()
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as exc:
            log.warning("Service de reconnaissance injoignable : %s", exc)
            return ""
        except Exception as exc:
            log.debug("Echec de transcription : %s", exc)
            return ""


# --------------------------------------------------------------------------
# Ecoute avec mesure du niveau sonore (pour l animation de l interface)
# --------------------------------------------------------------------------
SAMPLE_RATE = 16000
CHUNK = 1024
SAMPLE_WIDTH = 2          # int16
SILENCE_SECONDS = 0.9     # silence qui marque la fin d une phrase
# Une phrase breve -- « stop », « arrete », « pause » -- n a pas besoin d une
# aussi longue attente : elle est finie, et c est justement la qu on veut une
# reaction immediate. Au-dela de DUREE_BREVE de parole, on reprend l attente
# complete, car une phrase longue se dit souvent avec des respirations.
SILENCE_BREF = 0.6
DUREE_BREVE = 1.1
PRE_BUFFER_CHUNKS = 4     # on garde le debut du mot, avant le declenchement

# Etats remontes a l interface pendant l ecoute.
STATE_CALIBRATING = "calibration"
STATE_WAITING = "attente"
STATE_SPEAKING = "parole"
STATE_DONE = "termine"


def _rms(raw: bytes) -> float:
    """Niveau sonore moyen d un bloc audio, entre 0 et 1."""
    import array
    import math

    if not raw:
        return 0.0
    samples = array.array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if not samples:
        return 0.0
    total = 0
    for value in samples:
        total += value * value
    return min(1.0, math.sqrt(total / len(samples)) / 32768.0)


class LevelMeterListener:
    """
    Capture micro maison, qui expose le NIVEAU SONORE en direct.

    `speech_recognition.listen()` ne permet pas de suivre le volume pendant
    l ecoute : on gere donc nous-memes le flux PyAudio pour pouvoir animer
    l interface, puis on transmet l audio collecte au moteur de reconnaissance.

    Le seuil de declenchement est ADAPTATIF : beaucoup de micros integres ont
    un gain faible (sur cette machine, le bruit de fond plafonne a 0,0016).
    Un seuil fixe trop haut ne se declenche jamais ; on le derive donc du
    bruit ambiant mesure, avec un plancher volontairement bas.
    """

    # Plancher absolu : en dessous, on considere que c est du bruit de fond.
    #
    # Volontairement bas. Le bruit d une piece calme se mesure autour de
    # 0,00003 : un plancher a 0,004 vaut alors cent trente fois le bruit
    # reel, et il faut presque crier pour le franchir. C est surtout vrai
    # quand un media joue : l annulation d echo de la carte son efface le
    # son des haut-parleurs -- mesure a 0,00001, donc elle marche -- mais
    # elle attenue la voix par la meme occasion.
    PLANCHER = 0.0015
    # Multiplicateur applique au bruit ambiant mesure.
    FACTEUR = 3.5
    # Marge au-dessus du bruit le plus fort entendu pendant la calibration :
    # c est lui, et non la moyenne, qui dit ce qu il faut depasser.
    MARGE_PIC = 1.6
    # Au-dela, on demanderait de crier : mieux vaut quelques declenchements
    # a vide qu un assistant sourd.
    SEUIL_MAX = 0.04

    def __init__(self, plancher: float | None = None, facteur: float | None = None) -> None:
        self.plancher = self.PLANCHER if plancher is None else float(plancher)
        self.facteur = self.FACTEUR if facteur is None else float(facteur)
        self.ambient = 0.0
        self.threshold = self.plancher
        self.pic_recent = 0.0        # sert a l auto-gain de l animation
        self.pic_calibration = 0.0
        self._audio = None
        self._stream = None

    def _open_stream(self):
        import pyaudio

        audio = pyaudio.PyAudio()
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
        )
        return audio, stream

    def flux(self):
        """
        Le flux d entree, ouvert UNE SEULE FOIS et conserve.

        Ouvrir le micro coute cher : 488 ms la premiere fois sur la machine
        de reference, 200 ms ensuite. Or « Alma » se prononce en moins d une
        seconde. Rouvrir le flux a chaque ecoute creait donc une fenetre
        sourde a chaque tour de boucle, et une longue au tout debut : le
        premier appel passait a la trappe et il fallait le repeter.
        """
        if self._stream is not None:
            return self._stream
        self._audio, self._stream = self._open_stream()
        return self._stream

    def fermer(self) -> None:
        """Libere le micro (arret de l application)."""
        if self._stream is None:
            return
        audio, stream = self._audio, self._stream
        self._audio = self._stream = None
        self._close(audio, stream)

    def _rattraper(self, stream) -> list:
        """
        Vide le retard accumule pendant qu on ne lisait pas, en gardant les
        tout derniers instants.

        Le flux continue d enregistrer pendant qu Alma reflechit, execute et
        repond : sans cela on relirait sa propre voix. On conserve juste de
        quoi ne pas couper le debut d un mot prononce a l instant meme ou
        l ecoute reprend.
        """
        garde: list = []
        try:
            while stream.get_read_available() >= CHUNK:
                garde.append(stream.read(CHUNK, exception_on_overflow=False))
                del garde[:-PRE_BUFFER_CHUNKS]
        except Exception as exc:
            log.debug("Rattrapage impossible : %s", exc)
        return garde

    def _appliquer_seuil(self, ambient: float) -> float:
        """
        Seuil de declenchement : au-dessus du bruit, aussi bas que possible.

        Trois reperes, dont on garde le plus haut : le plancher absolu, un
        multiple du bruit moyen, et une marge au-dessus du pic entendu pendant
        la calibration. Le tout plafonne, car un seuil trop haut rend sourd.
        """
        self.ambient = ambient
        self.threshold = min(self.SEUIL_MAX, max(
            self.plancher,
            ambient * self.facteur,
            self.pic_calibration * self.MARGE_PIC,
        ))
        return self.threshold

    def niveau_affiche(self, niveau: float) -> float:
        """
        Convertit un niveau brut en valeur 0..1 pour l animation.

        Auto-gain : l echelle suit le pic recent, sinon une voix faible sur un
        micro peu sensible donnerait un orbe quasi immobile.
        """
        self.pic_recent = max(niveau, self.pic_recent * 0.995)
        echelle = max(self.threshold * 3.0, self.pic_recent, 0.01)
        return max(0.0, min(1.0, niveau / echelle))

    def calibrate(self, duration: float = 1.0, on_level=None) -> float:
        """Mesure le bruit ambiant et en deduit le seuil de declenchement."""
        try:
            stream = self.flux()
            self._rattraper(stream)
            blocs = max(1, int(duration * SAMPLE_RATE / CHUNK))
            niveaux = []
            for _ in range(blocs):
                niveau = _rms(stream.read(CHUNK, exception_on_overflow=False))
                niveaux.append(niveau)
                if on_level:
                    on_level(self.niveau_affiche(niveau), STATE_CALIBRATING)
            # On ignore les pics (claquement, toux) : moyenne des 70% les plus bas.
            niveaux.sort()
            retenus = niveaux[: max(1, int(len(niveaux) * 0.7))]
            # Le bruit le plus fort de la periode, hors valeur aberrante,
            # dit ce que le seuil doit depasser pour ne pas se declencher seul.
            self.pic_calibration = niveaux[int(len(niveaux) * 0.97)] if niveaux else 0.0
            return self._appliquer_seuil(sum(retenus) / len(retenus))
        except Exception as exc:
            log.debug("Calibration impossible : %s", exc)
            self.fermer()          # flux abime : la prochaine fois, on rouvre
            return self.threshold

    def listen(self, on_level=None, timeout: float = 8.0, phrase_limit: float = 12.0,
               doit_continuer=None):
        """
        Ecoute jusqu a detecter une phrase complete.

        `on_level(niveau_affiche, etat)` est appele a chaque bloc (~16 fois par
        seconde) : c est ce qui alimente l animation.
        `doit_continuer()` permet d interrompre proprement depuis l interface.
        Retourne les octets audio bruts, ou None si rien n a ete capte.
        """
        try:
            stream = self.flux()
        except Exception as exc:
            log.warning("Micro inaccessible : %s", exc)
            self.fermer()
            return None

        blocs_par_seconde = SAMPLE_RATE / CHUNK
        max_attente = int(timeout * blocs_par_seconde)
        max_phrase = int(phrase_limit * blocs_par_seconde)
        blocs_silence_fin = int(SILENCE_SECONDS * blocs_par_seconde)
        blocs_silence_bref = int(SILENCE_BREF * blocs_par_seconde)
        blocs_brefs = int(DUREE_BREVE * blocs_par_seconde)

        # Ce qui a ete capte pendant qu on ne lisait pas : on n en garde que
        # la fin, qui devient le debut du pre-tampon.
        pre_buffer: list = self._rattraper(stream)
        frames: list = []
        parle = False
        silence = 0
        blocs_forts = 0
        blocs_actifs = 0          # blocs reellement parles, silences exclus

        try:
            for index in range(max_attente + max_phrase):
                if doit_continuer is not None and not doit_continuer():
                    return b"".join(frames) if frames else None
                bloc = stream.read(CHUNK, exception_on_overflow=False)
                niveau = _rms(bloc)
                affiche = self.niveau_affiche(niveau)

                if not parle:
                    if on_level:
                        on_level(affiche, STATE_WAITING)
                    pre_buffer.append(bloc)
                    del pre_buffer[:-PRE_BUFFER_CHUNKS]
                    # Le bruit ambiant est reestime en continu tant qu on se tait,
                    # pour suivre les changements d environnement.
                    if niveau < self.threshold:
                        self._appliquer_seuil(self.ambient * 0.98 + niveau * 0.02)
                    # Deux blocs forts d affilee : c est une voix, pas un clic.
                    blocs_forts = blocs_forts + 1 if niveau > self.threshold else 0
                    if blocs_forts >= 2:
                        parle = True
                        frames.extend(pre_buffer)
                    elif index >= max_attente:
                        return None          # personne n a parle
                else:
                    if on_level:
                        on_level(affiche, STATE_SPEAKING)
                    frames.append(bloc)
                    if niveau <= self.threshold:
                        silence += 1
                    else:
                        silence = 0
                        blocs_actifs += 1
                    attendu = (blocs_silence_bref if blocs_actifs <= blocs_brefs
                               else blocs_silence_fin)
                    if silence >= attendu:
                        break
            return b"".join(frames) if frames else None
        except Exception as exc:
            log.debug("Echec de capture : %s", exc)
            self.fermer()          # flux abime : la prochaine fois, on rouvre
            return b"".join(frames) if frames else None
        finally:
            if on_level:
                on_level(0.0, STATE_DONE)

    @staticmethod
    def _close(audio, stream) -> None:
        for fermer in (
            lambda: stream.stop_stream(),
            lambda: stream.close(),
            lambda: audio.terminate(),
        ):
            try:
                fermer()
            except Exception:
                pass
