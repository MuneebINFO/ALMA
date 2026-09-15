"""
La caméra : prendre une photo, et ne pas marcher sur la capture d'écran.

Les deux phrases se ressemblent beaucoup — « prends une photo » et « prends
une photo de l'écran » — et c'est tout l'enjeu de ce fichier : elles ne
doivent pas atterrir au même endroit.

Le matériel n'est jamais touché ici : le fixture `aucune_trace_sur_la_machine`
pose une caméra fictive qui rend toujours la même image, et neutralise
l'écriture du fichier. Sans cela la suite allumerait le témoin de la webcam et
remplirait les Images de qui la lance (règle 4), et la commande ne se
routerait que sur les machines qui ont une caméra (règle 5).
"""

import pytest

from core import camera
from core.context import Utterance


def route(router, phrase):
    utterance = Utterance.parse(phrase, wake_words=["alma"])
    resolution = router.resolve(utterance, None)
    return resolution.command.name if resolution else "aucune"


# --------------------------------------------------------------------------
# Le routage
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "prends une photo",
    "prends une photo avec la caméra",
    "prends moi une photo",
    "photo",
    "take a photo",
    "take a picture",
    "take a selfie",
    "take a photo with the camera",
])
def test_ces_phrases_prennent_une_photo(router, phrase):
    assert route(router, phrase) == "camera_photo", phrase


@pytest.mark.parametrize("phrase", [
    "prends une capture d'écran",
    "prends une photo de l'écran",
    "screenshot",
    "take a screenshot",
])
def test_la_capture_d_ecran_n_est_pas_volee(router, phrase):
    """
    La régression la plus probable de ce module. « photo de l'écran » et
    « photo » ne diffèrent que par trois mots, et la caméra est déclarée plus
    prioritaire que la capture d'écran.
    """
    assert route(router, phrase) == "screenshot", phrase


def test_sans_camera_le_routeur_continue_de_chercher(router, monkeypatch):
    """
    Le guard laisse passer : sur une machine sans webcam, « photo » ne doit
    pas échouer ici, il doit aller voir ailleurs.
    """
    monkeypatch.setattr(camera, "lister", lambda: [])
    assert route(router, "prends une photo") != "camera_photo"


# --------------------------------------------------------------------------
# Les réponses, dans les deux langues
# --------------------------------------------------------------------------
def test_la_photo_est_confirmee_en_francais(assistant):
    reponse = assistant.handle("prends une photo")
    assert "enregistrée" in reponse.text.lower(), reponse.text


def test_la_photo_est_confirmee_en_anglais(assistant):
    reponse = assistant.handle("take a photo")
    assert "saved" in reponse.text.lower(), reponse.text


def test_une_camera_muette_le_dit_dans_les_deux_langues(assistant, monkeypatch):
    """
    Le cas le plus fréquent en vrai : la caméra existe, mais Windows en
    refuse l'accès. `capturer` rend alors des octets vides sans lever.
    """
    monkeypatch.setattr(camera, "capturer", lambda identifiant="": b"")

    fr = assistant.handle("prends une photo")
    assert not fr.ok, fr.text
    assert "confidentialité" in fr.text.lower(), fr.text

    en = assistant.handle("take a photo")
    assert not en.ok, en.text
    assert "privacy" in en.text.lower(), en.text


def test_un_disque_plein_ne_ment_pas(assistant, monkeypatch):
    """Si le fichier ne s'écrit pas, on ne dit pas que la photo est prise."""
    monkeypatch.setattr(camera, "enregistrer",
                        lambda image, dossier: (False, "disque plein"))

    reponse = assistant.handle("prends une photo")
    assert not reponse.ok, reponse.text
    assert "disque plein" in reponse.text


# --------------------------------------------------------------------------
# Le choix de la caméra
# --------------------------------------------------------------------------
def test_une_vraie_camera_l_emporte_sur_une_virtuelle():
    """
    Les pilotes virtuels — Lenovo, OBS, Teams — s'installent devant et sont
    listés en premier, alors qu'ils ne montrent souvent rien.
    """
    appareils = [("id-1", "Lenovo Virtual Camera"), ("id-2", "Integrated Camera")]
    assert camera.choisir(appareils) == ("id-2", "Integrated Camera")


def test_faute_de_mieux_on_prend_la_virtuelle():
    appareils = [("id-1", "OBS Virtual Camera")]
    assert camera.choisir(appareils) == ("id-1", "OBS Virtual Camera")


def test_sans_aucun_appareil_on_ne_rend_rien():
    assert camera.choisir([]) == ("", "")
