"""
Volume du lecteur contre volume de l'ordinateur.

Une vidéo de site de streaming a son propre curseur de volume, dans la page.
« baisse le volume de la vidéo » doit agir sur celui-là, « baisse le volume »
sur toute la machine — et les deux ne doivent jamais se confondre.
"""

import pytest

from core import desktop, media_control, player_volume, win_utils
from core.context import Utterance


@pytest.fixture
def lecteur_sur_ecran_2(monkeypatch):
    """Une vidéo joue dans Chrome sur l'écran 2, rien sur l'écran 1."""
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=10, titre="Bloc-notes", processus="notepad.exe", ecran=1),
        desktop.Fenetre(handle=20, titre="Interstellar - YouTube - Google Chrome",
                        processus="chrome.exe", ecran=2),
    ])
    monkeypatch.setattr(media_control, "sessions", lambda: [
        media_control.SessionMedia("Chrome", "Interstellar", media_control.EN_LECTURE),
    ])


class CurseurFactice:
    """
    Un curseur de lecteur : il ne bouge qu'aux flèches, par pas fixe, et se
    bloque à ses bornes — comme un vrai.
    """

    HAUT, BAS = player_volume.VK_HAUT, player_volume.VK_BAS

    def __init__(self, valeur=50.0, pas=5.0, sourd=False):
        self._valeur = float(valeur)
        self.pas = float(pas)
        self.sourd = sourd
        self.touches = 0

    @property
    def valeur(self):
        return self._valeur

    def appuyer(self, code):
        self.touches += 1
        if self.sourd:
            return True
        if code == self.HAUT:
            self._valeur = min(100.0, self._valeur + self.pas)
        elif code == self.BAS:
            self._valeur = max(0.0, self._valeur - self.pas)
        return True


@pytest.fixture
def curseur(monkeypatch):
    """Installe un curseur factice à la place de celui de la page."""
    def installer(valeur=50.0, pas=5.0, sourd=False, absent=False):
        faux = CurseurFactice(valeur, pas, sourd)
        monkeypatch.setattr(player_volume, "trouver",
                            lambda fenetre: None if absent else faux)
        monkeypatch.setattr(player_volume, "_preparer", lambda fenetre, c: True)
        monkeypatch.setattr(win_utils, "press_key", faux.appuyer)
        # Les temporisations n'ont d'intérêt qu'en face d'un vrai navigateur.
        monkeypatch.setattr(player_volume, "PAUSE_TOUCHE", 0)
        monkeypatch.setattr(player_volume, "PAUSE_LECTURE", 0)
        return faux
    return installer


@pytest.fixture
def volume_general(monkeypatch):
    """Le volume de la machine, pour vérifier qu'il ne bouge pas."""
    etat = {"niveau": 50}
    monkeypatch.setattr(win_utils, "get_volume", lambda: etat["niveau"])
    monkeypatch.setattr(win_utils, "set_volume",
                        lambda n: etat.__setitem__("niveau", int(n)) or True)
    monkeypatch.setattr(win_utils, "change_volume",
                        lambda d: etat.__setitem__("niveau", etat["niveau"] + d)
                        or etat["niveau"])
    return etat


# --------------------------------------------------------------------------
# Les deux familles de phrases ne doivent pas se marcher dessus
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("baisse le volume de la vidéo à 30", "volume_media_set"),
    ("mets le volume du film à 60", "volume_media_set"),
    ("augmente le volume de la vidéo à 80", "volume_media_set"),
    ("baisse le volume de la vidéo", "volume_media_down"),
    ("mets la vidéo moins fort", "volume_media_down"),
    ("monte le volume de la vidéo", "volume_media_up"),
    ("mets le film plus fort", "volume_media_up"),
    # Sans objet, c'est le volume de l'ordinateur.
    ("baisse le volume à 30", "volume_set"),
    ("mets le volume à 30", "volume_set"),
    ("volume à 70", "volume_set"),
    ("monte le son", "volume_up"),
    ("baisse le son", "volume_down"),
    ("coupe le son", "volume_mute"),
])
def test_le_volume_vise_est_le_bon(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == attendu, phrase


# --------------------------------------------------------------------------
# Le pas du lecteur est mesure, pas suppose
# --------------------------------------------------------------------------
@pytest.mark.parametrize("pas", [1.0, 2.0, 5.0, 10.0, 20.0])
def test_la_cible_est_atteinte_quel_que_soit_le_pas_du_lecteur(curseur, pas):
    """
    YouTube avance par 5, un autre lecteur par 10. Le code mesure le pas réel
    après la première salve : la cible doit être atteinte dans les deux cas,
    sans marteler le clavier.
    """
    faux = curseur(valeur=50.0, pas=pas)
    atteint = player_volume.regler(object(), 20)
    assert abs(atteint - 20) <= player_volume.TOLERANCE, "pas de " + str(pas)
    assert faux.touches <= player_volume.TOUCHES_MAX * 2, "trop d'appuis"


def test_les_bornes_sont_respectees(curseur):
    curseur(valeur=50.0, pas=5.0)
    assert player_volume.regler(object(), 0) == 0
    curseur(valeur=50.0, pas=5.0)
    assert player_volume.regler(object(), 100) == 100


def test_un_lecteur_sourd_aux_fleches_narrete_le_martelage(curseur):
    """Si rien ne bouge, on s'arrête au lieu d'insister indéfiniment."""
    faux = curseur(valeur=50.0, sourd=True)
    assert player_volume.regler(object(), 10) == 50
    assert faux.touches <= player_volume.TOUCHES_MAX, "il a insisté pour rien"


def test_sans_curseur_de_volume(curseur):
    curseur(absent=True)
    assert player_volume.regler(object(), 30) is None
    assert player_volume.lire(object()) is None


@pytest.mark.parametrize("nom,attendu", [
    ("Volume", True), ("volume", True), ("Curseur de volume", True),
    ("Volumen", True), ("Sound", True),
    ("Barre de lecture", False), ("Lecture", False), ("Plein écran", False),
    ("", False), (None, False),
])
def test_reconnaissance_du_curseur_de_volume(nom, attendu):
    """La barre de progression ne doit jamais être prise pour le volume."""
    assert player_volume._est_un_volume(nom) is attendu


# --------------------------------------------------------------------------
# A travers l assistant
# --------------------------------------------------------------------------
def test_le_volume_de_la_video_ne_touche_pas_celui_de_lordinateur(
        assistant, lecteur_sur_ecran_2, curseur, volume_general):
    curseur(valeur=80.0, pas=5.0)
    assistant.definir_ecran(2)
    reponse = assistant.handle("baisse le volume de la vidéo à 30")
    assert reponse.ok, reponse.text
    assert "30" in reponse.text
    assert volume_general["niveau"] == 50, "le volume général devait rester intact"


def test_le_volume_de_lordinateur_ne_touche_pas_celui_de_la_video(
        assistant, lecteur_sur_ecran_2, curseur, volume_general):
    faux = curseur(valeur=80.0, pas=5.0)
    assistant.definir_ecran(2)
    assert assistant.handle("mets le volume à 20").ok
    assert volume_general["niveau"] == 20
    assert faux.valeur == 80, "le lecteur devait rester intact"


@pytest.mark.parametrize("phrase,attendu", [
    ("monte le volume de la vidéo", 60),
    ("baisse le volume de la vidéo", 40),
    ("mets la vidéo plus fort", 60),
    ("mets le film moins fort", 40),
])
def test_les_paliers_de_dix(assistant, lecteur_sur_ecran_2, curseur,
                            phrase, attendu):
    faux = curseur(valeur=50.0, pas=5.0)
    assistant.definir_ecran(2)
    assert assistant.handle(phrase).ok, phrase
    assert faux.valeur == attendu, phrase


def test_rien_ne_joue_sur_lecran_de_travail(assistant, lecteur_sur_ecran_2,
                                            curseur, volume_general):
    """Comme pour la pause : on ne va pas régler un lecteur d'un autre écran."""
    faux = curseur(valeur=80.0, pas=5.0)
    assistant.definir_ecran(1)
    reponse = assistant.handle("baisse le volume de la vidéo à 30")
    assert not reponse.ok
    assert "écran 1" in reponse.text
    assert faux.touches == 0, "le lecteur de l'écran 2 devait être épargné"


def test_un_lecteur_sans_curseur_le_dit_clairement(assistant, lecteur_sur_ecran_2,
                                                   curseur):
    curseur(absent=True)
    assistant.definir_ecran(2)
    reponse = assistant.handle("baisse le volume de la vidéo à 30")
    assert not reponse.ok
    assert "volume" in reponse.text.lower()


# --------------------------------------------------------------------------
# Quelle fenetre regler
# --------------------------------------------------------------------------
def test_la_fenetre_de_lecture_est_celle_de_lecran(lecteur_sur_ecran_2):
    fenetres = media_control.fenetres_de_lecture_sur_ecran(2)
    assert [f.handle for f in fenetres] == [20]
    assert media_control.fenetres_de_lecture_sur_ecran(1) == []


def test_un_lecteur_sans_session_declaree_est_quand_meme_trouve(monkeypatch):
    """
    Beaucoup de sites de streaming n'exposent aucune session média : leur
    fenêtre se reconnaît alors à son titre.
    """
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=30, titre="Detective Conan | Anime-Sama - Streaming",
                        processus="firefox.exe", ecran=2),
    ])
    monkeypatch.setattr(media_control, "sessions", lambda: [])
    fenetres = media_control.fenetres_de_lecture_sur_ecran(2)
    assert [f.handle for f in fenetres] == [30]
