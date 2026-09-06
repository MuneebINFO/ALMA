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
        self._calibre = False     # la calibration n a lieu qu une fois
        # Vrai quand la derniere ecoute a capte de la parole, meme si la
        # transcription a echoue : c est la difference entre « je n ai rien
        # entendu » et « je n ai pas compris ».
        self.a_capte = False
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
                peripherique=self.config.get("voice.input_device") if self.config else None,
            )
        return self._meter

    def listen_live(self, on_level=None, timeout: float = 8.0,
                    phrase_limit: float = 12.0, doit_continuer=None,
                    toutes: bool = False):
        """
        Comme listen(), mais en remontant le NIVEAU SONORE en direct via
        `on_level(niveau, etat)`. Utilise par l interface graphique pour
        montrer que la voix est bien detectee pendant que l on parle.

        `doit_continuer()` permet d interrompre l ecoute proprement.
        `toutes` renvoie toutes les hypotheses du moteur au lieu de la
        meilleure : l assistant peut alors choisir celle qui correspond a une
        commande connue.
        """
        if not self.available:
            return ""
        import speech_recognition as sr

        compteur = self._compteur()
        # Une seule calibration : la relancer a chaque ecoute laissait une
        # zone morte de 0,8 s par cycle, pendant laquelle la parole etait
        # avalee par la mesure du bruit de fond.
        if not self._calibre:
            compteur.calibrate(0.8, on_level=on_level)
            self._calibre = True

        brut = compteur.listen(
            on_level=on_level, timeout=timeout,
            phrase_limit=phrase_limit, doit_continuer=doit_continuer,
        )
        self.a_capte = bool(brut)
        if not brut:
            return [] if toutes else ""
        # L audio est etiquete a SA frequence reelle : le moteur de
        # reconnaissance s en sert pour interpreter les echantillons.
        audio = sr.AudioData(brut, compteur.taux, SAMPLE_WIDTH)
        if toutes:
            return self._transcribe_all(audio)
        return self._transcribe(audio)

    def recalibrate(self, duration: float = 1.0, on_level=None) -> float:
        """Remesure le bruit ambiant (utile si l environnement change)."""
        seuil = self._compteur().calibrate(duration, on_level=on_level)
        self._calibre = True
        return seuil

    def niveau_maximum(self, duree: float = 3.0) -> float:
        """
        Pic sonore observe pendant `duree`. Sert a dire a l utilisateur si son
        micro capte quelque chose, sans dependre du seuil de declenchement.
        """
        compteur = self._compteur()
        audio = flux = None
        try:
            audio, flux = compteur._open_stream()
            pics = []
            for _ in range(max(1, int(duree * compteur.taux / CHUNK))):
                pics.append(_rms(flux.read(CHUNK, exception_on_overflow=False)))
            return max(pics) if pics else 0.0
        except Exception as exc:
            log.debug("Mesure du niveau impossible : %s", exc)
            return 0.0
        finally:
            compteur._close(audio, flux)

    def _transcribe_all(self, audio) -> list:
        """
        Toutes les hypotheses du moteur, de la plus probable a la moins.

        La reconnaissance se trompe souvent sur les mots courts et les mots
        anglais dans une phrase francaise (« scroll » entendu « Paul »). La
        bonne transcription figure frequemment dans les hypotheses suivantes :
        l assistant peut alors choisir celle qui correspond a une commande.
        """
        if self.engine == "vosk" and self._vosk_model is not None:
            unique = self._transcribe(audio)
            return [unique] if unique else []
        try:
            brut = self._recognizer.recognize_google(
                audio, language=self.language, show_all=True
            )
        except Exception as exc:
            log.debug("Hypotheses indisponibles : %s", exc)
            unique = self._transcribe(audio)
            return [unique] if unique else []

        propositions = []
        if isinstance(brut, dict):
            for entree in brut.get("alternative", []) or []:
                texte = str(entree.get("transcript", "")).strip()
                if texte:
                    propositions.append(texte)
        elif isinstance(brut, list):
            for entree in brut:
                texte = str(getattr(entree, "transcript", entree) or "").strip()
                if texte:
                    propositions.append(texte)
        elif isinstance(brut, str) and brut.strip():
            propositions.append(brut.strip())

        propositions = list(dict.fromkeys(propositions))
        if not propositions:
            # Filet de securite : la voie « hypotheses multiples » ne doit
            # jamais rendre moins que la transcription simple.
            unique = self._transcribe(audio)
            if unique:
                propositions = [unique]
        return propositions

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
# Duree de son conservee AVANT le declenchement, pour ne pas amputer l attaque
# du premier mot. Exprimee en SECONDES et non en blocs : un nombre de blocs
# fixe represente une duree differente selon la frequence d echantillonnage,
# et couperait le debut des mots des que le micro tourne plus vite.
PRE_BUFFER_SECONDES = 0.40

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


# Ordre de preference des interfaces audio de Windows. WASAPI donne le signal
# le plus propre ; DirectSound est place en dernier car, sur certaines cartes,
# il renvoie un flux sature en permanence (mesure : 0,6 de niveau en silence).
PREFERENCE_API = ("wasapi", "mme", "wdm", "directsound")

# Au-dela de ce niveau en ambiance calme, le flux n est pas exploitable :
# le peripherique renvoie du bruit sature plutot que du son.
AMBIANT_ABERRANT = 0.05

# Peripheriques a ecarter : ce ne sont pas des micros.
EXCLUS = ("stereo mix", "mixage stereo", "sound mapper", "mappeur de sons",
          "pc speaker", "output", "sortie", "loopback")


def peripheriques_entree(audio) -> list:
    """Micros disponibles, du plus prometteur au moins."""
    try:
        defaut = audio.get_default_input_device_info()
        nom_defaut = str(defaut.get("name", "")).lower()
    except Exception:
        nom_defaut = ""

    candidats = []
    for index in range(audio.get_device_count()):
        try:
            info = audio.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) < 1:
                continue
            nom = str(info.get("name", ""))
            if any(mot in nom.lower() for mot in EXCLUS):
                continue
            api = str(audio.get_host_api_info_by_index(info["hostApi"])["name"]).lower()
            rang_api = next(
                (i for i, cle in enumerate(PREFERENCE_API) if cle in api.replace(" ", "")),
                len(PREFERENCE_API),
            )
            # On privilegie le peripherique que Windows a choisi par defaut,
            # mais via l interface la plus performante.
            meme_micro = 0 if (nom_defaut and nom_defaut[:18] in nom.lower()) else 1
            candidats.append((meme_micro, rang_api, index, nom,
                              int(info.get("defaultSampleRate", 44100))))
        except Exception:
            continue
    candidats.sort()
    return [(index, nom, rate) for _m, _a, index, nom, rate in candidats]


def choisir_peripherique(audio, demande=None):
    """
    Retourne (index, taux) du micro a utiliser.

    `demande` peut etre un numero, un morceau de nom, ou None pour laisser
    le choix automatique.
    """
    liste = peripheriques_entree(audio)
    if demande not in (None, "", "auto"):
        if isinstance(demande, int) or str(demande).isdigit():
            index = int(demande)
            for i, nom, rate in liste:
                if i == index:
                    return i, rate
            try:
                info = audio.get_device_info_by_index(index)
                return index, int(info.get("defaultSampleRate", 44100))
            except Exception:
                pass
        else:
            voulu = str(demande).lower()
            for i, nom, rate in liste:
                if voulu in nom.lower():
                    return i, rate
    # On ne se fie pas au classement seul : on VERIFIE que le peripherique
    # rend un signal plausible. Certains pilotes acceptent l ouverture puis
    # renvoient du bruit sature, ce qui rendrait toute detection impossible.
    for index, _nom, rate in liste:
        if _flux_plausible(audio, index, rate):
            return index, rate
    if liste:
        index, _nom, rate = liste[0]
        return index, rate
    return None, SAMPLE_RATE


def _flux_plausible(audio, index, rate, blocs: int = 8) -> bool:
    """Le peripherique rend-il un niveau credible en ambiance calme ?"""
    import pyaudio

    flux = None
    try:
        flux = audio.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True,
                          frames_per_buffer=CHUNK, input_device_index=index)
        niveaux = [_rms(flux.read(CHUNK, exception_on_overflow=False)) for _ in range(blocs)]
        return (sum(niveaux) / len(niveaux)) < AMBIANT_ABERRANT
    except Exception:
        return False
    finally:
        if flux is not None:
            try:
                flux.stop_stream(); flux.close()
            except Exception:
                pass


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

    # Plancher absolu de detection.
    #
    # Il est volontairement TRES bas, pour une raison de dissymetrie : un
    # declenchement de trop ne coute rien -- l enonce sera ignore faute de mot
    # d appel -- alors qu un declenchement manque rend l assistant sourd.
    # Mesures sur un micro integre : bruit de fond moyen 0,0001, pics 0,0016.
    PLANCHER = 0.0010
    # Multiplicateur applique au bruit ambiant mesure.
    FACTEUR = 3.5

    def __init__(self, plancher: float | None = None, facteur: float | None = None,
                 peripherique=None) -> None:
        self.plancher = self.PLANCHER if plancher is None else float(plancher)
        self.peripherique = peripherique
        self.taux = SAMPLE_RATE
        self.index_peripherique = None
        self.facteur = self.FACTEUR if facteur is None else float(facteur)
        self.ambient = 0.0
        self.threshold = self.plancher
        self.pic_recent = 0.0        # sert a l auto-gain de l animation

    def _open_stream(self):
        """
        Ouvre le micro a sa frequence NATIVE, sur l interface la plus
        sensible. Forcer 16 kHz sur MME divisait le signal par cinq.
        """
        import pyaudio

        audio = pyaudio.PyAudio()
        index, taux = choisir_peripherique(audio, self.peripherique)
        try:
            stream = audio.open(
                format=pyaudio.paInt16, channels=1, rate=taux, input=True,
                frames_per_buffer=CHUNK, input_device_index=index,
            )
        except Exception:
            # Le peripherique choisi refuse ces reglages : on retombe sur
            # celui de Windows, aux valeurs historiques.
            stream = audio.open(
                format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                input=True, frames_per_buffer=CHUNK,
            )
            taux = SAMPLE_RATE
            index = None
        self.taux = taux
        self.index_peripherique = index
        return audio, stream

    def _appliquer_seuil(self, ambient: float) -> float:
        self.ambient = ambient
        self.threshold = max(self.plancher, ambient * self.facteur)
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
        audio = stream = None
        try:
            audio, stream = self._open_stream()
            blocs = max(1, int(duration * self.taux / CHUNK))
            niveaux = []
            for _ in range(blocs):
                niveau = _rms(stream.read(CHUNK, exception_on_overflow=False))
                niveaux.append(niveau)
                if on_level:
                    on_level(self.niveau_affiche(niveau), STATE_CALIBRATING)
            # On ignore les pics (claquement, toux) : moyenne des 70% les plus bas.
            niveaux.sort()
            retenus = niveaux[: max(1, int(len(niveaux) * 0.7))]
            return self._appliquer_seuil(sum(retenus) / len(retenus))
        except Exception as exc:
            log.debug("Calibration impossible : %s", exc)
            return self.threshold
        finally:
            self._close(audio, stream)

    def listen(self, on_level=None, timeout: float = 8.0, phrase_limit: float = 12.0,
               doit_continuer=None):
        """
        Ecoute jusqu a detecter une phrase complete.

        `on_level(niveau_affiche, etat)` est appele a chaque bloc (~16 fois par
        seconde) : c est ce qui alimente l animation.
        `doit_continuer()` permet d interrompre proprement depuis l interface.
        Retourne les octets audio bruts, ou None si rien n a ete capte.
        """
        audio = stream = None
        try:
            audio, stream = self._open_stream()
        except Exception as exc:
            log.warning("Micro inaccessible : %s", exc)
            self._close(audio, stream)
            return None

        blocs_par_seconde = self.taux / CHUNK
        max_attente = int(timeout * blocs_par_seconde)
        max_phrase = int(phrase_limit * blocs_par_seconde)
        blocs_silence_fin = int(SILENCE_SECONDS * blocs_par_seconde)
        # Amorce et confirmation, calculees a partir de la frequence reelle.
        blocs_amorce = max(2, int(PRE_BUFFER_SECONDES * blocs_par_seconde))
        blocs_confirmation = max(2, int(0.12 * blocs_par_seconde))

        pre_buffer: list = []
        frames: list = []
        parle = False
        silence = 0
        blocs_forts = 0

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
                    del pre_buffer[:-blocs_amorce]
                    # Le bruit ambiant est reestime en continu tant qu on se tait,
                    # pour suivre les changements d environnement.
                    if niveau < self.threshold:
                        self._appliquer_seuil(self.ambient * 0.98 + niveau * 0.02)
                    # Un son bref est un clic, pas une voix : on exige une
                    # DUREE de son fort, elle aussi independante de la
                    # frequence d echantillonnage.
                    blocs_forts = blocs_forts + 1 if niveau > self.threshold else 0
                    if blocs_forts >= blocs_confirmation:
                        parle = True
                        frames.extend(pre_buffer)
                    elif index >= max_attente:
                        return None          # personne n a parle
                else:
                    if on_level:
                        on_level(affiche, STATE_SPEAKING)
                    frames.append(bloc)
                    silence = silence + 1 if niveau <= self.threshold else 0
                    if silence >= blocs_silence_fin:
                        break
            return b"".join(frames) if frames else None
        except Exception as exc:
            log.debug("Echec de capture : %s", exc)
            return b"".join(frames) if frames else None
        finally:
            if on_level:
                on_level(0.0, STATE_DONE)
            self._close(audio, stream)

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
