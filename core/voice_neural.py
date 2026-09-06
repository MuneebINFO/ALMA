"""
Voix neuronale (edge-tts) : nettement plus humaine que SAPI5.

edge-tts utilise le service de synthese de Microsoft Edge : gratuit, SANS
cle API et sans compte. Il faut simplement une connexion internet ; si elle
manque, l appelant retombe automatiquement sur la voix SAPI5 locale.

La lecture du MP3 passe par MCI (winmm), inclus dans Windows : aucune
bibliotheque audio supplementaire a installer.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import threading
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# Voix feminines francaises les plus naturelles proposees par le service.
VOIX_RECOMMANDEES = (
    "fr-FR-DeniseNeural",       # France, chaleureuse et posee
    "fr-FR-EloiseNeural",       # France, plus jeune
    "fr-BE-CharlineNeural",     # Belgique
    "fr-CH-ArianeNeural",       # Suisse
    "fr-CA-SylvieNeural",       # Canada
)
VOIX_PAR_DEFAUT = "fr-FR-DeniseNeural"

_verrou_mci = threading.Lock()
# Alias de la lecture en cours, pour pouvoir la couper depuis un autre thread.
_alias_courant = None


def _mci(commande: str) -> int:
    """Envoie une commande a l interface multimedia de Windows."""
    import ctypes

    return ctypes.windll.winmm.mciSendStringW(commande, None, 0, None)


def jouer_fichier(chemin: Path) -> bool:
    """
    Joue un MP3 via MCI (aucune dependance externe).

    L appel est bloquant, mais l alias est publie AVANT la lecture : un autre
    thread peut ainsi couper la parole en cours (voir arreter_lecture).
    """
    global _alias_courant

    alias = "alma_" + uuid.uuid4().hex[:8]
    try:
        with _verrou_mci:
            if _mci('open "' + str(chemin) + '" type mpegvideo alias ' + alias) != 0:
                return False
            _alias_courant = alias
        # La lecture se fait HORS du verrou : sinon l interruption ne pourrait
        # pas prendre la main pendant qu on parle.
        _mci("play " + alias + " wait")
        return True
    except Exception as exc:
        log.debug("Lecture MCI impossible : %s", exc)
        return False
    finally:
        with _verrou_mci:
            if _alias_courant == alias:
                _alias_courant = None
        try:
            _mci("close " + alias)
        except Exception:
            pass


def arreter_lecture() -> bool:
    """Coupe la lecture en cours. True s il y en avait une."""
    with _verrou_mci:
        alias = _alias_courant
    if not alias:
        return False
    try:
        _mci("stop " + alias)
        return True
    except Exception as exc:
        log.debug("Arret de lecture impossible : %s", exc)
        return False


class VoixNeuronale:
    """Synthese vocale neuronale, avec lecture immediate."""

    def __init__(self, voix: str = VOIX_PAR_DEFAUT, vitesse: str = "+0%", volume: str = "+0%") -> None:
        self.voix = voix or VOIX_PAR_DEFAUT
        self.vitesse = vitesse
        self.volume = volume
        self.disponible = False
        self.erreur = ""
        self._dossier = Path(tempfile.gettempdir()) / "alma_voix"
        self._cache = self._dossier / "cache"
        self._verifier()

    def _verifier(self) -> None:
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            self.erreur = "edge-tts n'est pas installé (pip install edge-tts)."
            return
        try:
            self._dossier.mkdir(parents=True, exist_ok=True)
            self._cache.mkdir(parents=True, exist_ok=True)
            self.disponible = True
        except Exception as exc:
            self.erreur = "Dossier temporaire inaccessible : " + str(exc)

    def _chemin_cache(self, texte: str) -> Path:
        """Un fichier par phrase : les repliques courtes se rejouent sans reseau."""
        empreinte = hashlib.sha1(
            (self.voix + "|" + self.vitesse + "|" + texte).encode("utf-8")
        ).hexdigest()[:16]
        return self._cache / (empreinte + ".mp3")

    def synthetiser(self, texte: str, cacher: bool = False) -> Path | None:
        """
        Genere un MP3 pour le texte. Retourne None en cas d echec (hors ligne).
        Si `cacher` est vrai, le fichier est conserve et reutilise : c est ce
        qui rend les repliques d activation (« Oui ? ») instantanees.
        """
        if not self.disponible or not texte.strip():
            return None
        import asyncio

        import edge_tts

        if cacher:
            cible = self._chemin_cache(texte)
            if cible.exists() and cible.stat().st_size > 0:
                return cible
        else:
            cible = self._dossier / (uuid.uuid4().hex + ".mp3")

        async def produire() -> None:
            communicate = edge_tts.Communicate(
                texte, self.voix, rate=self.vitesse, volume=self.volume
            )
            await communicate.save(str(cible))

        try:
            asyncio.run(produire())
        except Exception as exc:
            log.debug("Synthèse neuronale impossible : %s", exc)
            self.erreur = str(exc)
            return None
        return cible if cible.exists() and cible.stat().st_size > 0 else None

    def dire(self, texte: str, cacher: bool = False) -> bool:
        """Synthetise puis joue. Retourne False si l appelant doit basculer sur SAPI5."""
        fichier = self.synthetiser(texte, cacher=cacher)
        if fichier is None:
            return False
        try:
            return jouer_fichier(fichier)
        finally:
            if not cacher:
                try:
                    fichier.unlink()
                except Exception:
                    pass

    def prechauffer(self, phrases) -> int:
        """
        Pre-synthetise des phrases courtes au demarrage pour qu elles soient
        jouees instantanement ensuite (accuse de reception du mot d appel).
        """
        pretes = 0
        for phrase in phrases:
            if self.synthetiser(phrase, cacher=True) is not None:
                pretes += 1
        return pretes

    def nettoyer(self) -> None:
        """Supprime les fichiers audio temporaires restants."""
        try:
            for fichier in self._dossier.glob("*.mp3"):
                try:
                    fichier.unlink()
                except Exception:
                    pass
        except Exception:
            pass
