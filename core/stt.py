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
import threading

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
        self._whisper = None
        self._meter = None        # compteur de niveau, cree a la demande
        # Pourquoi la derniere transcription a rendu une chaine vide :
        # "incompris", "injoignable", "panne", ou "" si tout allait bien.
        self.derniere_raison = ""
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
        elif self.engine == "whisper":
            self._init_whisper()

    def _init_whisper(self) -> None:
        """
        Charge Whisper, qui transcrit SUR LA MACHINE.

        Interet : rien ne part chez Google. Prix : le modele met une trentaine
        de secondes a se charger, puis une a trois secondes par phrase sur
        processeur, la ou l API repond en deux cents millisecondes. Mesure
        faite ici sur des phrases de test : il n est pas plus juste que Google
        sur les noms propres, qui sont pourtant le point faible commun aux
        deux. A choisir pour la confidentialite, pas pour la precision.
        """
        import sys
        import types

        taille = str(self.config.get("voice.whisper_model", "small")
                     if self.config else "small") or "small"
        # `av` ne sert qu a DECODER DES FICHIERS audio ; nous fournissons du
        # PCM brut. Sur une machine ou le controle d application de Windows
        # bloque sa DLL, ce bouchon evite un echec qui n a pas lieu d etre.
        if "av" not in sys.modules:
            try:
                import av  # noqa: F401
            except Exception:
                sys.modules["av"] = types.ModuleType("av")
        try:
            from faster_whisper.transcribe import WhisperModel

            self._whisper = WhisperModel(taille, device="cpu", compute_type="int8")
        except Exception as exc:
            self.error = ("Whisper indisponible (" + str(exc)
                          + ") : repli sur le moteur Google.")
            log.warning(self.error)
            self.engine = "google"

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
                    phrase_limit: float = 12.0, doit_continuer=None,
                    voix_active=None) -> str:
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
            # A LA PREMIERE ecoute seulement. C est un piege quand on invite
            # quelqu un a parler : il clique, il parle, et sa voix est mesuree
            # comme le bruit de la piece -- le seuil monte au plafond et le
            # micro devient sourd. Appeler `preparer()` pendant qu on affiche
            # la consigne evite d en arriver la.
            compteur.calibrate(0.8, on_level=on_level)

        brut = compteur.listen(
            on_level=on_level, timeout=timeout,
            phrase_limit=phrase_limit, doit_continuer=doit_continuer,
            voix_active=voix_active,
        )
        if not brut:
            return ""
        _garder_la_prise(brut)
        audio = sr.AudioData(normaliser(brut), SAMPLE_RATE, SAMPLE_WIDTH)
        return self._transcribe(audio)

    def preparer(self) -> bool:
        """
        Mesure le bruit ambiant MAINTENANT, sans rien ecouter d autre.

        A appeler pendant qu on affiche « dites-le a voix haute » : la mesure
        se fait alors sur le silence, et non sur la voix qu on vient de
        demander. Retourne False si le micro n est pas disponible.
        """
        if not self.available:
            return False
        compteur = self._compteur()
        if compteur.ambient == 0.0 and compteur.threshold == compteur.plancher:
            compteur.calibrate(0.8)
        return True

    def recalibrate(self, duration: float = 1.0, on_level=None) -> float:
        """Remesure le bruit ambiant (utile si l environnement change)."""
        return self._compteur().calibrate(duration, on_level=on_level)

    def fermer(self) -> None:
        """Libere le micro. Le flux est garde ouvert tant qu on ecoute."""
        if self._meter is not None:
            self._meter.fermer()

    # Ce que Whisper ecrit quand il n entend que du silence : le modele a ete
    # entraine sur des sous-titres, et il en reproduit les mentions. Les
    # laisser passer ferait executer des commandes fantomes.
    HALLUCINATIONS = (
        "sous-titres realises par", "sous-titrage", "amara.org",
        "merci d avoir regarde", "merci a tous", "abonnez vous",
        "sous-titres par la communaute", "thanks for watching",
    )

    def _transcrire_whisper(self, audio) -> str:
        """Transcription locale, sans reseau."""
        import numpy as np

        from core import text_utils

        brut = audio.get_raw_data(convert_rate=SAMPLE_RATE, convert_width=2)
        echantillons = np.frombuffer(brut, dtype=np.int16).astype(np.float32) / 32768.0
        try:
            segments, _info = self._whisper.transcribe(
                echantillons, language=self.language.split("-")[0], beam_size=5,
            )
            texte = " ".join(s.text for s in segments).strip()
        except Exception as exc:
            log.debug("Echec Whisper : %s", exc)
            return ""
        norme = text_utils.normalize(texte)
        if any(mention in norme for mention in self.HALLUCINATIONS):
            return ""
        return texte

    def _transcribe(self, audio) -> str:
        import speech_recognition as sr

        # Une chaine vide a trois causes tres differentes -- pas de mot
        # reconnaissable, service injoignable, ou panne -- et le geste a faire
        # n est pas le meme. `derniere_raison` les distingue pour qui veut le
        # dire a l utilisateur (voir le premier lancement).
        self.derniere_raison = ""

        if self.engine == "whisper" and self._whisper is not None:
            return self._transcrire_whisper(audio)
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
            self.derniere_raison = "incompris"
            return ""
        except sr.RequestError as exc:
            self.derniere_raison = "injoignable"
            log.warning("Service de reconnaissance injoignable : %s", exc)
            return ""
        except Exception as exc:
            self.derniere_raison = "panne"
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


# Niveau vise apres normalisation, en fraction de la pleine echelle. 0,7
# laisse de la marge : pousser a 1,0 ferait saturer le moindre depassement,
# et la saturation s entend comme un gresillement que rien ne transcrit.
CIBLE_NORMALISATION = 0.70
# Au-dela, on amplifierait du souffle. Un enregistrement reellement vide
# doit le rester : le multiplier par mille ne cree pas de la parole.
GAIN_MAXIMAL = 40.0


def _garder_la_prise(brut: bytes) -> None:
    """
    Ecrit la derniere prise sur le disque, si ALMA_DIAG_CAPTURE le demande.

    Quand la reconnaissance ne rend rien alors que le niveau bougeait, la
    seule facon de trancher est d ECOUTER ce qui a ete capte : une voix mal
    transcrite et un flux corrompu produisent le meme vu-metre. Eteint par
    defaut -- rien ne s ecrit sans qu on l ait demande.
    """
    import os

    dossier = os.environ.get("ALMA_DIAG_CAPTURE", "")
    if not dossier or not brut:
        return
    try:
        import time
        import wave
        from pathlib import Path

        cible = Path(dossier)
        cible.mkdir(parents=True, exist_ok=True)
        chemin = cible / ("prise_%.0f.wav" % (time.time() * 1000))
        with wave.open(str(chemin), "wb") as fichier:
            fichier.setnchannels(1)
            fichier.setsampwidth(SAMPLE_WIDTH)
            fichier.setframerate(SAMPLE_RATE)
            fichier.writeframes(brut)
        log.warning("Prise conservée : %s (%d octets)", chemin, len(brut))
    except Exception as exc:
        log.debug("Prise non conservée : %s", exc)


def normaliser(brut: bytes) -> bytes:
    """
    Remonte le niveau d un enregistrement avant de le transcrire.

    Beaucoup de micros integres capturent tres bas : sur cette machine, le
    bruit de fond se mesure a 0,000015, soit cent fois moins que la normale.
    La voix suit -- elle arrive donc au moteur de reconnaissance trente
    decibels sous ce qu il attend, et il ne rend rien. On voit alors la bille
    bouger (le son EST la) sans qu aucun mot ne revienne.

    Le niveau sonore mesure pour le declenchement, lui, n est pas touche :
    il decrit la piece, pas ce qu on envoie a Google.
    """
    import array

    if not brut:
        return brut
    echantillons = array.array("h")
    echantillons.frombytes(brut[: len(brut) - (len(brut) % 2)])
    if not echantillons:
        return brut
    pic = max(abs(v) for v in echantillons)
    if pic == 0:
        return brut
    gain = min(GAIN_MAXIMAL, CIBLE_NORMALISATION * 32767 / pic)
    if gain <= 1.05:
        return brut                    # deja au bon niveau : ne rien toucher
    for i, valeur in enumerate(echantillons):
        echantillons[i] = max(-32768, min(32767, int(valeur * gain)))
    return echantillons.tobytes()


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
    # Mesure sur la machine de reference, micro integre, piece calme : le
    # bruit de fond tient entre 0,000015 et 0,000023, et le bloc le plus
    # fort d une seconde de silence monte a 0,0006. Un plancher a 0,0015
    # valait donc pres de cent fois le bruit reel : il fallait parler fort
    # pour le franchir, et c etait pire quand un media jouait, car
    # l annulation d echo de la carte son attenue la voix en meme temps que
    # les haut-parleurs. A 0,0004 le plancher reste vingt-cinq fois au-dessus
    # du silence, ce qui suffit -- et deux blocs consecutifs sont exiges pour
    # declencher, ce qui ecarte deja les clics et les claquements.
    PLANCHER = 0.0004
    # Multiplicateur applique au bruit ambiant mesure.
    FACTEUR = 3.5
    # Marge au-dessus du bruit le plus fort entendu recemment : c est lui,
    # et non la moyenne, qui dit ce qu il faut depasser.
    MARGE_PIC = 1.6
    # Le pic redescend tout seul pendant les silences : applique a chaque
    # bloc (environ seize par seconde), ce facteur le divise par deux en
    # quinze secondes. Sans cela, un claquement de porte pendant la
    # calibration rendait sourd pour le reste de la session. Un bruit qui
    # DURE, lui, releve le pic a chaque bloc : la decroissance ne concerne
    # que ce qui est deja passe.
    DECROISSANCE_PIC = 0.997
    # Au-dela, on demanderait de crier : mieux vaut quelques declenchements
    # a vide qu un assistant sourd.
    SEUIL_MAX = 0.04
    # Ce qu il faut depasser QUAND ALMA PARLE, en multiple du seuil ordinaire.
    #
    # Le micro reentend les haut-parleurs. L annulation d echo de la carte son
    # en retire l essentiel, mais pas tout -- et depuis que le plancher est
    # descendu a 0,0004, ce qui reste suffisait a declencher : Alma se coupait
    # la parole a elle-meme au milieu de « Je vous ecoute ». Une voix qui
    # s adresse au micro est franchement plus forte que ce retour attenue ;
    # exiger ce facteur pendant qu elle parle laisse passer l une et pas
    # l autre. Voir `dire_maintenant` dans gui.py pour l autre moitie.
    FACTEUR_PENDANT_LA_PAROLE = 3.0

    def __init__(self, plancher: float | None = None, facteur: float | None = None) -> None:
        self.plancher = self.PLANCHER if plancher is None else float(plancher)
        self.facteur = self.FACTEUR if facteur is None else float(facteur)
        self.ambient = 0.0
        self.threshold = self.plancher
        self.pic_recent = 0.0        # sert a l auto-gain de l animation
        self.pic_ambiant = 0.0       # le bloc de silence le plus fort, recent
        self._audio = None
        self._stream = None
        self._proprietaire = None      # thread qui a ouvert le flux

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

        UN SEUL THREAD doit s en servir. PortAudio ne survit pas a une
        lecture faite depuis un thread autre que celui qui a ouvert le flux :
        cela ne leve pas, cela plante le processus (segfault, sans trace
        Python). L appelant qui change de thread doit donc fermer d abord.
        On se contente ici de le SIGNALER -- fermer depuis le mauvais thread
        serait tout aussi hasardeux.
        """
        if self._stream is not None:
            if self._proprietaire not in (None, threading.current_thread().name):
                log.warning(
                    "Flux micro ouvert par « %s », lu depuis « %s » : "
                    "PortAudio n aime pas cela du tout.",
                    self._proprietaire, threading.current_thread().name)
            return self._stream
        self._audio, self._stream = self._open_stream()
        self._proprietaire = threading.current_thread().name
        return self._stream

    def fermer(self) -> None:
        """Libere le micro (arret de l application)."""
        if self._stream is None:
            return
        audio, stream = self._audio, self._stream
        self._audio = self._stream = None
        self._proprietaire = None
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
        multiple du bruit moyen, et une marge au-dessus du bloc de silence le
        plus fort entendu recemment. Le tout plafonne, car un seuil trop haut
        rend sourd.
        """
        self.ambient = ambient
        self.threshold = min(self.SEUIL_MAX, max(
            self.plancher,
            ambient * self.facteur,
            self.pic_ambiant * self.MARGE_PIC,
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
            # Le bruit le plus fort de la periode dit ce que le seuil doit
            # depasser pour ne pas se declencher seul -- mais le plus fort au
            # sens strict, c etait le claquement de touche qu on voulait
            # justement ecarter. On jette donc le cinquieme superieur.
            self.pic_ambiant = niveaux[max(0, int(len(niveaux) * 0.8) - 1)] if niveaux else 0.0
            return self._appliquer_seuil(sum(retenus) / len(retenus))
        except Exception as exc:
            log.debug("Calibration impossible : %s", exc)
            self.fermer()          # flux abime : la prochaine fois, on rouvre
            return self.threshold

    def listen(self, on_level=None, timeout: float = 8.0, phrase_limit: float = 12.0,
               doit_continuer=None, voix_active=None):
        """
        Ecoute jusqu a detecter une phrase complete.

        `on_level(niveau_affiche, etat)` est appele a chaque bloc (~16 fois par
        seconde) : c est ce qui alimente l animation.
        `doit_continuer()` permet d interrompre proprement depuis l interface.
        `voix_active()` dit si l assistant est en train de parler : le seuil de
        declenchement est alors releve, pour ne pas prendre sa propre voix
        renvoyee par les haut-parleurs pour celle de l utilisateur.
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
                    # pour suivre les changements d environnement -- son pic
                    # comme sa moyenne. Le pic monte d un coup si la piece
                    # devient bruyante, et redescend tout seul ensuite.
                    if niveau < self.threshold:
                        self.pic_ambiant = max(niveau,
                                               self.pic_ambiant * self.DECROISSANCE_PIC)
                        self._appliquer_seuil(self.ambient * 0.98 + niveau * 0.02)
                    # Deux blocs forts d affilee : c est une voix, pas un clic.
                    # Et pendant qu Alma parle, il en faut franchement plus :
                    # sinon c est son propre echo qui la declenche.
                    exige = self.threshold
                    if voix_active is not None and voix_active():
                        exige *= self.FACTEUR_PENDANT_LA_PAROLE
                    blocs_forts = blocs_forts + 1 if niveau > exige else 0
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
