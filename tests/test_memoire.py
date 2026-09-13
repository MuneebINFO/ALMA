"""
Ce qu'Alma retient d'une session à l'autre.

À ne pas confondre avec les notes, qui sont des pense-bêtes datés, ni avec le
contexte de session, qui expire au bout d'une minute. Un souvenir est un fait
durable — une préférence, un proche, un projet — et se rappelle par son sujet.
"""

import pytest

from core.context import Utterance
from core.storage import JsonCollection


@pytest.fixture
def memoire(assistant, tmp_path):
    """Un fichier de souvenirs isolé, pour ne pas toucher à celui de la machine."""
    assistant.storage.souvenirs = JsonCollection(tmp_path / "souvenirs.json")
    return assistant


def retenir(assistant, *faits):
    for fait in faits:
        assistant.handle("retiens que " + fait)


# --------------------------------------------------------------------------
# Retenir
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "retiens que je suis allergique aux arachides",
    "souviens-toi que ma sœur s'appelle Yasmine",
    "mémorise que mon projet sort en octobre",
    "rappelle-toi que je déteste le café",
])
def test_les_formulations_pour_retenir(memoire, phrase):
    reponse = memoire.handle(phrase)
    assert reponse.ok, reponse.text
    assert len(memoire.storage.souvenirs.load()) == 1


def test_un_fait_retenu_est_conserve(memoire):
    memoire.handle("retiens que je suis allergique aux arachides")
    souvenirs = memoire.storage.souvenirs.load()
    assert souvenirs[0]["text"] == "je suis allergique aux arachides"
    assert "created_at" in souvenirs[0]


def test_retenir_deux_fois_la_meme_chose_ne_duplique_pas(memoire):
    memoire.handle("retiens que je suis allergique aux arachides")
    reponse = memoire.handle("retiens que Je Suis Allergique aux arachides.")
    assert "savais déjà" in reponse.text
    assert len(memoire.storage.souvenirs.load()) == 1


def test_retenir_ne_se_commente_pas_a_voix_haute(memoire):
    """Une action se voit ; seule une question reçoit une réponse parlée."""
    assert memoire.handle("retiens que j'aime le thé").speak is False


@pytest.mark.parametrize("phrase", ["retiens que", "retiens que a"])
def test_rien_a_retenir(memoire, phrase):
    reponse = memoire.handle(phrase)
    assert not reponse.ok or memoire.storage.souvenirs.load() == []


# --------------------------------------------------------------------------
# Rappeler
# --------------------------------------------------------------------------
def test_sans_rien_en_memoire(memoire):
    assert "rien" in memoire.handle("qu'est-ce que tu sais sur moi").text.lower()


def test_rappeler_tout(memoire):
    retenir(memoire, "j'aime le thé", "ma sœur s'appelle Yasmine")
    reponse = memoire.handle("de quoi te souviens-tu")
    assert reponse.ok and reponse.speak is True
    assert "thé" in reponse.text and "Yasmine" in reponse.text


def test_rappeler_par_sujet(memoire):
    retenir(memoire, "j'aime le thé", "ma sœur s'appelle Yasmine",
            "mon projet ALMA sort en octobre")
    reponse = memoire.handle("qu'est-ce que tu sais sur ma sœur")
    assert "Yasmine" in reponse.text
    assert "thé" not in reponse.text, "un sujet précis ne doit pas tout ressortir"


def test_un_sujet_inconnu_le_dit(memoire):
    retenir(memoire, "j'aime le thé")
    assert "rien" in memoire.handle("qu'est-ce que tu sais sur le tennis").text.lower()


def test_une_longue_memoire_est_resumee(memoire):
    retenir(memoire, *["fait numéro " + str(i) for i in range(9)])
    reponse = memoire.handle("de quoi te souviens-tu")
    assert "9 choses" in reponse.text
    assert reponse.text.count(";") <= 4, "on n'en cite que quelques-unes"


def test_rappeler_est_une_question_donc_parle(memoire):
    retenir(memoire, "j'aime le thé")
    assert memoire.handle("qu'est-ce que tu sais sur le thé").speak is True


# --------------------------------------------------------------------------
# Oublier
# --------------------------------------------------------------------------
def test_oublier_un_sujet(memoire):
    retenir(memoire, "je suis allergique aux arachides", "ma sœur s'appelle Yasmine")
    reponse = memoire.handle("oublie que je suis allergique aux arachides")
    assert reponse.ok, reponse.text
    restants = [s["text"] for s in memoire.storage.souvenirs.load()]
    assert restants == ["ma sœur s'appelle Yasmine"]


def test_oublier_nemporte_pas_les_souvenirs_voisins(memoire):
    """Un seul mot en commun ne doit pas suffire à effacer."""
    retenir(memoire, "ma sœur s'appelle Yasmine", "mon frère s'appelle Karim")
    memoire.handle("oublie que ma sœur s'appelle Yasmine")
    restants = [s["text"] for s in memoire.storage.souvenirs.load()]
    assert restants == ["mon frère s'appelle Karim"]


def test_oublier_un_sujet_inconnu(memoire):
    retenir(memoire, "j'aime le thé")
    reponse = memoire.handle("oublie que je fais du parapente")
    assert len(memoire.storage.souvenirs.load()) == 1, reponse.text


def test_tout_oublier(memoire):
    retenir(memoire, "j'aime le thé", "ma sœur s'appelle Yasmine")
    memoire.handle("oublie tout")
    assert memoire.storage.souvenirs.load() == []


# --------------------------------------------------------------------------
# Ne pas marcher sur les commandes voisines
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("retiens que j'aime le thé", "memoire_retenir"),
    ("qu'est-ce que tu sais sur moi", "memoire_rappeler"),
    ("oublie que j'aime le thé", "memoire_oublier"),
    # Celles-là appartiennent aux notes et aux rappels.
    ("note que je dois rappeler ma banque", "add_note"),
    ("lis mes notes", "read_notes"),
    ("supprime la note 2", "delete_note"),
    ("rappelle-moi dans 10 minutes de sortir le gâteau", "set_reminder"),
])
def test_les_commandes_voisines_ne_sont_pas_captees(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == attendu, phrase


def test_les_souvenirs_restent_sur_la_machine():
    """
    Un fichier en clair, relisible sans passer par Alma.

    La vérification porte sur la configuration PAR DÉFAUT, et non sur celle
    de la suite de tests : cette dernière écrit dans un dossier temporaire,
    justement pour ne pas toucher aux souvenirs de qui lance les tests.
    """
    from config import load_config
    from core.storage import Storage

    chemin = Storage(load_config()).souvenirs.path
    assert chemin.name == "souvenirs.json"
    assert "data" in str(chemin).replace("\\", "/")
