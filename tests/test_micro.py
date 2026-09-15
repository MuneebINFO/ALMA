"""
Le micro reste ouvert entre deux écoutes.

Le symptôme : en début de session, le premier « Alma » ne déclenchait rien et
il fallait appeler une seconde fois. La cause était mécanique — le flux audio
était rouvert à chaque écoute, ce qui coûte 488 ms la première fois et environ
200 ms ensuite, sur la machine de référence. « Alma » se prononce en moins
d'une seconde : le premier appel tombait entièrement dans cette fenêtre sourde.
"""

import pytest

from core import stt
from core.stt import (CHUNK, PRE_BUFFER_CHUNKS, SAMPLE_RATE,
                      LevelMeterListener)


class FluxFactice:
    """Un flux d'entrée : il rend des blocs silencieux, et compte les lectures."""

    def __init__(self, disponible=0, niveau=b"\x00\x00"):
        self.lectures = 0
        self.ferme = False
        self.disponible = disponible          # blocs déjà en attente
        self._bloc = niveau * (CHUNK)

    def read(self, taille, exception_on_overflow=True):
        self.lectures += 1
        if self.disponible > 0:
            self.disponible -= 1
        return self._bloc

    def get_read_available(self):
        return self.disponible * CHUNK

    def stop_stream(self):
        pass

    def close(self):
        self.ferme = True


class AudioFactice:
    def __init__(self):
        self.termine = False

    def terminate(self):
        self.termine = True


@pytest.fixture
def ecouteur(monkeypatch):
    """Un écouteur dont chaque ouverture de flux est comptée."""
    ouvertures = []

    def ouvrir(self):
        flux = FluxFactice()
        ouvertures.append(flux)
        return AudioFactice(), flux

    monkeypatch.setattr(LevelMeterListener, "_open_stream", ouvrir)
    e = LevelMeterListener()
    e.ouvertures = ouvertures
    return e


# --------------------------------------------------------------------------
# Le flux est unique
# --------------------------------------------------------------------------
def test_le_micro_nest_ouvert_quune_fois(ecouteur):
    """C'est tout le correctif : une ouverture, pas une par écoute."""
    ecouteur.calibrate(0.2)
    for _ in range(4):
        ecouteur.listen(timeout=0.2, phrase_limit=0.2)
    assert len(ecouteur.ouvertures) == 1, "le micro a été rouvert"


def test_le_meme_flux_est_rendu_a_chaque_fois(ecouteur):
    assert ecouteur.flux() is ecouteur.flux()


def test_fermer_libere_le_micro(ecouteur):
    flux = ecouteur.flux()
    ecouteur.fermer()
    assert flux.ferme, "le flux devait être fermé"
    assert ecouteur._stream is None
    # Et une écoute suivante le rouvre proprement.
    ecouteur.listen(timeout=0.2, phrase_limit=0.2)
    assert len(ecouteur.ouvertures) == 2


def test_fermer_deux_fois_ne_casse_rien(ecouteur):
    ecouteur.flux()
    ecouteur.fermer()
    ecouteur.fermer()
    assert ecouteur._stream is None


def test_un_flux_abime_est_rouvert_a_lecoute_suivante(ecouteur, monkeypatch):
    """Si une lecture échoue, on repart sur un flux neuf plutôt que d'insister."""
    flux = ecouteur.flux()

    def casser(taille, exception_on_overflow=True):
        raise OSError("peripherique retire")

    monkeypatch.setattr(flux, "read", casser)
    assert ecouteur.listen(timeout=0.2, phrase_limit=0.2) is None
    assert ecouteur._stream is None, "le flux abimé devait être lâché"
    ecouteur.listen(timeout=0.2, phrase_limit=0.2)
    assert len(ecouteur.ouvertures) == 2


# --------------------------------------------------------------------------
# Le retard accumule
# --------------------------------------------------------------------------
def test_le_retard_est_vide_mais_la_fin_est_gardee():
    """
    Le flux enregistre pendant qu'Alma réfléchit, exécute et répond. On jette
    ce retard — sinon on relirait sa propre voix — sauf les tout derniers
    instants, qui servent à ne pas couper le début d'un mot.
    """
    e = LevelMeterListener()
    flux = FluxFactice(disponible=40)         # ~2,5 s de retard
    garde = e._rattraper(flux)
    assert len(garde) == PRE_BUFFER_CHUNKS
    assert flux.disponible == 0, "tout le retard devait être lu"


def test_sans_retard_le_rattrapage_ne_lit_rien():
    e = LevelMeterListener()
    flux = FluxFactice(disponible=0)
    assert e._rattraper(flux) == []
    assert flux.lectures == 0


def test_le_rattrapage_survit_a_un_flux_qui_proteste(monkeypatch):
    e = LevelMeterListener()
    flux = FluxFactice(disponible=5)
    monkeypatch.setattr(flux, "get_read_available",
                        lambda: (_ for _ in ()).throw(OSError("ferme")))
    assert e._rattraper(flux) == []


def test_lecoute_demarre_avec_le_pre_tampon_du_rattrapage(ecouteur, monkeypatch):
    """
    Ce qui a été dit juste avant que l'écoute reprenne doit être conservé :
    c'est la fenêtre où l'ancien code perdait le mot d'appel.
    """
    vus = []
    vrai_rattrapage = LevelMeterListener._rattraper

    def espion(self, flux):
        blocs = vrai_rattrapage(self, flux)
        vus.append(len(blocs))
        return blocs

    monkeypatch.setattr(LevelMeterListener, "_rattraper", espion)
    ecouteur.flux().disponible = 10
    ecouteur.listen(timeout=0.2, phrase_limit=0.2)
    assert vus and vus[0] == PRE_BUFFER_CHUNKS


# --------------------------------------------------------------------------
# Cablage cote application
# --------------------------------------------------------------------------
def test_la_synthese_du_micro_est_exposee_par_le_module_stt(monkeypatch):
    """L'interface doit pouvoir rendre le micro à la fermeture."""
    moteur = stt.SpeechToText.__new__(stt.SpeechToText)
    ferme = []
    moteur._meter = type("M", (), {"fermer": lambda _s: ferme.append(True)})()
    moteur.fermer()
    assert ferme == [True]


def test_fermer_sans_micro_ouvert_ne_casse_rien():
    moteur = stt.SpeechToText.__new__(stt.SpeechToText)
    moteur._meter = None
    moteur.fermer()


# --------------------------------------------------------------------------
# Fin de phrase : plus vite quand la phrase est breve
# --------------------------------------------------------------------------
BLOC_FORT = bytes([0, 0x40]) * CHUNK      # niveau ~0,5 : franchement au-dessus
BLOC_SILENCE = bytes(2) * CHUNK


class FluxScripte:
    """Un flux qui rejoue une suite de blocs decidee a l'avance."""

    def __init__(self, blocs):
        self.blocs = list(blocs)
        self.lus = 0

    def read(self, taille, exception_on_overflow=True):
        self.lus += 1
        if self.blocs:
            return self.blocs.pop(0)
        return BLOC_SILENCE

    def get_read_available(self):
        return 0

    def stop_stream(self):
        pass

    def close(self):
        pass


def blocs(secondes):
    return int(secondes * SAMPLE_RATE / CHUNK)


def ecouter(duree_parole, monkeypatch):
    """Fait entendre `duree_parole` de voix, puis du silence. Rend le nombre
    de blocs lus avant que l'écoute ne se termine."""
    flux = FluxScripte([BLOC_FORT] * blocs(duree_parole))
    ecouteur = LevelMeterListener()
    monkeypatch.setattr(ecouteur, "flux", lambda: flux)
    monkeypatch.setattr(ecouteur, "_rattraper", lambda f: [])
    ecouteur.threshold = 0.01
    ecouteur.listen(timeout=5.0, phrase_limit=12.0)
    return flux.lus - blocs(duree_parole)


def test_une_phrase_breve_se_termine_plus_vite(monkeypatch):
    """
    « arrête » ne demande pas d'attendre neuf dixièmes de seconde : la phrase
    est finie, et c'est justement là qu'on veut une réaction immédiate.
    """
    silence = ecouter(0.5, monkeypatch)
    assert blocs(stt.SILENCE_BREF) <= silence <= blocs(stt.SILENCE_BREF) + 2


def test_une_phrase_longue_garde_lattente_complete(monkeypatch):
    """Une phrase longue se dit avec des respirations : on ne la coupe pas."""
    silence = ecouter(2.0, monkeypatch)
    assert blocs(stt.SILENCE_SECONDS) <= silence <= blocs(stt.SILENCE_SECONDS) + 2


def test_le_seuil_de_brievete_est_bien_place():
    assert stt.SILENCE_BREF < stt.SILENCE_SECONDS
    assert 0.5 <= stt.SILENCE_BREF <= 0.8


# --------------------------------------------------------------------------
# Le seuil ne reste pas coince en haut
# --------------------------------------------------------------------------
def bloc(niveau: float) -> bytes:
    """Un bloc audio dont le RMS vaut a peu pres `niveau` (0..1)."""
    import struct

    echantillon = max(-32767, min(32767, int(niveau * 32768)))
    return struct.pack("<h", echantillon) * CHUNK


def test_la_calibration_ecarte_le_claquement(monkeypatch):
    """
    Le bloc le plus fort d'une seconde de « silence » est rarement le bruit
    de la pièce : c'est une touche de clavier, un craquement de chaise. Le
    retenir tel quel fixait le seuil à 1,6 fois ce bruit-là pour toute la
    session -- et il fallait parler fort pour le franchir.
    """
    calme = [bloc(0.00002)] * 17 + [bloc(0.02)]        # dix-huit blocs, un claquement
    flux = FluxScripte(calme)
    ecouteur = LevelMeterListener()
    monkeypatch.setattr(ecouteur, "flux", lambda: flux)
    monkeypatch.setattr(ecouteur, "_rattraper", lambda f: [])

    ecouteur.calibrate(1.2)
    assert ecouteur.pic_ambiant < 0.001, "le claquement a été pris pour le bruit ambiant"
    assert ecouteur.threshold == ecouteur.plancher


def test_un_pic_transitoire_finit_par_redescendre(monkeypatch):
    """
    Et s'il passe quand même -- il a duré plus d'un cinquième de la mesure --
    il doit s'effacer tout seul. Une porte qui claque ne rend pas sourd pour
    le reste de la session.
    """
    ecouteur = LevelMeterListener()
    ecouteur.pic_ambiant = 0.02
    ecouteur._appliquer_seuil(0.00002)
    assert ecouteur.threshold > 0.03, "au départ : sourd"

    flux = FluxScripte([])          # que du silence, indéfiniment
    monkeypatch.setattr(ecouteur, "flux", lambda: flux)
    monkeypatch.setattr(ecouteur, "_rattraper", lambda f: [])
    for _ in range(13):             # treize attentes de 8 s : moins de 2 min
        ecouteur.listen(timeout=8.0, phrase_limit=0.5)

    assert ecouteur.threshold == ecouteur.plancher, (
        "le seuil est resté en haut : %.5f" % ecouteur.threshold)


def test_un_bruit_qui_dure_tient_le_seuil_en_haut(monkeypatch):
    """Le pendant : la décroissance ne doit pas rendre sourd au vrai bruit."""
    ecouteur = LevelMeterListener()
    flux = FluxScripte([bloc(0.003)] * 400)
    monkeypatch.setattr(ecouteur, "flux", lambda: flux)
    monkeypatch.setattr(ecouteur, "_rattraper", lambda f: [])
    ecouteur.pic_ambiant = 0.003
    ecouteur._appliquer_seuil(0.003)
    ecouteur.listen(timeout=8.0, phrase_limit=0.5)
    assert ecouteur.threshold > 0.004, "un bruit continu doit tenir le seuil au-dessus"


# --------------------------------------------------------------------------
# Le niveau envoyé à la reconnaissance
# --------------------------------------------------------------------------
# Symptôme : la bille bouge — le son EST là — mais rien ne revient. Beaucoup
# de micros intégrés capturent très bas ; sur la machine de référence le bruit
# de fond se mesure à 0,000015, cent fois moins que la normale. La voix suit,
# et arrive au moteur trente décibels sous ce qu'il attend.
def onde(fraction, n=4000):
    """Une sinusoïde dont le pic vaut `fraction` de la pleine échelle."""
    import array
    import math

    return array.array(
        "h", [int(fraction * 32767 * math.sin(i / 12)) for i in range(n)]
    ).tobytes()


def pic(brut):
    import array

    echantillons = array.array("h")
    echantillons.frombytes(brut)
    return max(abs(v) for v in echantillons) / 32767 if echantillons else 0.0


@pytest.mark.parametrize("depart", [0.01, 0.05, 0.2])
def test_une_voix_trop_faible_est_remontee(depart):
    apres = pic(stt.normaliser(onde(depart)))
    assert apres > depart * 3, "une prise très basse doit être franchement remontée"
    assert apres <= 0.71, "et jamais poussée jusqu'à la saturation"


def test_une_prise_deja_correcte_n_est_pas_touchee():
    """Retoucher ce qui va déjà bien ne peut qu'abîmer."""
    avant = onde(0.9)
    assert stt.normaliser(avant) == avant


def test_le_silence_reste_le_silence():
    """Multiplier du souffle par mille ne crée pas de la parole."""
    import array

    vide = array.array("h", [0] * 2000).tobytes()
    assert stt.normaliser(vide) == vide
    assert stt.normaliser(b"") == b""


def test_le_gain_est_plafonne():
    """Sinon un enregistrement quasi muet deviendrait un mur de souffle."""
    assert pic(stt.normaliser(onde(0.001))) < 0.5


def test_le_niveau_mesure_pour_declencher_n_est_pas_touche():
    """
    La normalisation ne concerne que ce qu'on ENVOIE. Le niveau qui décide du
    déclenchement décrit la pièce : le gonfler fausserait le seuil.
    """
    import inspect

    source = inspect.getsource(stt.LevelMeterListener.listen)
    assert "normaliser" not in source


# --------------------------------------------------------------------------
# Le diagnostic de capture
# --------------------------------------------------------------------------
# Quand la reconnaissance ne rend rien alors que le niveau bougeait, la seule
# façon de trancher est d'ÉCOUTER ce qui a été capté : une voix mal transcrite
# et un flux corrompu donnent le même vu-mètre. Mais un enregistreur laissé
# allumé serait un enregistreur de la voix de l'utilisateur, à son insu.
def test_rien_n_est_enregistre_sans_qu_on_le_demande(tmp_path, monkeypatch):
    monkeypatch.delenv("ALMA_DIAG_CAPTURE", raising=False)
    stt._garder_la_prise(b"\x01\x02" * 1000)
    assert list(tmp_path.iterdir()) == []


def test_la_prise_est_conservee_quand_on_le_demande(tmp_path, monkeypatch):
    import wave

    monkeypatch.setenv("ALMA_DIAG_CAPTURE", str(tmp_path))
    stt._garder_la_prise(b"\x01\x02" * 1000)

    fichiers = list(tmp_path.glob("*.wav"))
    assert len(fichiers) == 1
    with wave.open(str(fichiers[0])) as f:
        assert f.getframerate() == stt.SAMPLE_RATE
        assert f.getnchannels() == 1


def test_une_prise_vide_n_ecrit_rien(tmp_path, monkeypatch):
    monkeypatch.setenv("ALMA_DIAG_CAPTURE", str(tmp_path))
    stt._garder_la_prise(b"")
    assert list(tmp_path.iterdir()) == []


def test_le_flux_retient_qui_l_a_ouvert(ecouteur):
    """
    PortAudio ne survit pas à une lecture depuis un autre thread que celui
    qui a ouvert le flux — et il ne lève pas, il plante le processus. On ne
    peut pas l'en empêcher depuis Python ; on peut rendre la faute visible.
    """
    import threading

    ecouteur.flux()
    assert ecouteur._proprietaire == threading.current_thread().name
    ecouteur.fermer()
    assert ecouteur._proprietaire is None
