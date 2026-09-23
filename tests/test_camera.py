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


def test_une_camera_refusee_par_windows_le_dit(assistant, monkeypatch):
    """
    Windows sait POURQUOI, et le dire évite un quart d'heure perdu : envoyer
    quelqu'un fouiller les réglages de confidentialité quand la caméra est
    simplement prise par Zoom est une fausse piste coûteuse.
    """
    from core import permissions

    monkeypatch.setattr(camera, "capturer", lambda identifiant="": b"")
    monkeypatch.setattr(
        permissions, "explication",
        lambda capacite, langue="fr": ("Windows bloque la caméra."
                                       if langue != "en"
                                       else "Windows is blocking the camera."))

    fr = assistant.handle("prends une photo")
    assert not fr.ok, fr.text
    assert "bloque" in fr.text.lower(), fr.text

    en = assistant.handle("take a photo")
    assert "blocking" in en.text.lower(), en.text


def test_une_camera_autorisee_mais_muette_cherche_ailleurs(assistant, monkeypatch):
    """
    Autorisation accordée et pourtant rien : ce n'est PAS un problème de
    réglages, et le message ne doit pas y renvoyer. Le fixture laisse tout
    autorisé, ce qui est le cas nominal.
    """
    monkeypatch.setattr(camera, "capturer", lambda identifiant="": b"")

    fr = assistant.handle("prends une photo")
    assert not fr.ok, fr.text
    assert "autre application" in fr.text.lower(), fr.text
    assert "confidentialité" not in fr.text.lower(),         "on envoie l'utilisateur dans les réglages sans raison"

    en = assistant.handle("take a photo")
    assert "another application" in en.text.lower(), en.text


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


# --------------------------------------------------------------------------
# Regarder : la frontière entre les deux éditions passe ici
# --------------------------------------------------------------------------
@pytest.fixture
def edition_complete(assistant, monkeypatch):
    """
    Une machine où l'utilisateur a posé sa clé, avec un modèle factice.

    C'est `assistant.config` qu'il faut régler, pas le fixture `config` :
    l'assistant de test construit volontairement la sienne, isolée, pour
    qu'un test qui renomme Alma ne renomme pas celle de qui lance la suite.
    """
    from core import ai_fallback, secrets

    monkeypatch.setattr(secrets, "lire",
                        lambda nom, cfg=None: "sk-ant-fausse-cle")
    assistant.config.set("general.edition", "complete")

    vues = []

    class ModeleFactice:
        name = "claude_api"

        def generate(self, query, langue="fr"):
            return "réponse"

        def analyser_image(self, image, question, langue="fr"):
            vues.append((image, question, langue))
            return "Une tasse à café bleue."

    monkeypatch.setattr(ai_fallback, "get_provider", lambda cfg: ModeleFactice())
    return vues


@pytest.mark.parametrize("phrase", [
    "analyse ce que j'ai dans la main",
    "regarde ce que j'ai dans la main",
    "qu'est-ce que je tiens",
    "what am I holding",
    "what's in my hand",
])
def test_ces_phrases_analysent_la_main(router, phrase):
    assert route(router, phrase) == "camera_analyser_main", phrase


@pytest.mark.parametrize("phrase", [
    "qu'est-ce que tu vois",
    "regarde avec la caméra",
    "what do you see",
])
def test_ces_phrases_decrivent_la_scene(router, phrase):
    assert route(router, phrase) == "camera_decrire", phrase


def test_en_edition_libre_alma_le_dit_sans_rien_envoyer(assistant, monkeypatch):
    """
    La photo n'est même PAS prise : inutile d'allumer la caméra pour une
    analyse qu'on ne peut pas faire. Et la phrase dite n'est pas « je n'ai
    pas compris » — Alma a très bien compris.
    """
    from core import edition

    prises = []
    monkeypatch.setattr(camera, "capturer",
                        lambda identifiant="": prises.append(1) or b"jpeg")

    reponse = assistant.handle("analyse ce que j'ai dans la main")

    assert not reponse.ok
    assert reponse.text == edition.SANS_REGARD_FR
    assert prises == [], "la caméra a été allumée pour rien"


def test_en_edition_libre_en_anglais_aussi(assistant):
    from core import edition

    reponse = assistant.handle("what am I holding")

    assert reponse.text == edition.SANS_REGARD_EN


def test_en_edition_complete_l_image_part_entiere(assistant, edition_complete):
    """
    Sans recadrage : un modèle de vision retrouve une main tout seul, et
    détourer aurait coûté 180 Mo de dépendances pour une fraction de centime.
    """
    reponse = assistant.handle("analyse ce que j'ai dans la main")

    assert reponse.ok, reponse.text
    assert reponse.text == "Une tasse à café bleue."
    assert len(edition_complete) == 1
    image, question, langue = edition_complete[0]
    assert image == b"jpeg-de-test", "l'image envoyée n'est pas celle de la caméra"
    assert "main" in question
    assert langue == "fr"


def test_la_question_posee_au_modele_suit_la_langue(assistant, edition_complete):
    assistant.handle("what am I holding")

    _image, question, langue = edition_complete[0]
    assert langue == "en"
    assert "hand" in question and "main" not in question


def test_decrire_et_analyser_ne_posent_pas_la_meme_question(assistant,
                                                            edition_complete):
    assistant.handle("analyse ce que j'ai dans la main")
    assistant.handle("qu'est-ce que tu vois")

    main = edition_complete[0][1]
    scene = edition_complete[1][1]
    assert main != scene
    assert "main" in main and "main" not in scene


def test_une_camera_muette_ne_fait_rien_partir(assistant, edition_complete,
                                               monkeypatch):
    """Pas d'image, pas d'appel : on ne paie pas pour envoyer du vide."""
    monkeypatch.setattr(camera, "capturer", lambda identifiant="": b"")

    reponse = assistant.handle("analyse ce que j'ai dans la main")

    assert not reponse.ok
    assert edition_complete == [], "un appel est parti sans image"


def test_un_modele_en_panne_le_dit(assistant, monkeypatch):
    """Une erreur réseau doit s'entendre, pas remonter en exception."""
    from core import ai_fallback, secrets

    monkeypatch.setattr(secrets, "lire", lambda nom, cfg=None: "sk-ant-fausse-cle")
    assistant.config.set("general.edition", "complete")

    class ModeleEnPanne:
        name = "claude_api"

        def analyser_image(self, image, question, langue="fr"):
            raise RuntimeError("connexion refusée")

    monkeypatch.setattr(ai_fallback, "get_provider", lambda cfg: ModeleEnPanne())

    reponse = assistant.handle("analyse ce que j'ai dans la main")

    assert not reponse.ok
    assert "connexion refusée" in reponse.text
