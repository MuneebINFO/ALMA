"""
Tests du mot d appel et de la machine a etats de l ecoute.

Regle : l assistant entend tout, mais n agit que si son nom a ete prononce
(ou s il vient d etre reveille).
"""

import copy

import pytest

from config import Config
from core.wake import (
    ACCUSES,
    COMMANDE,
    IGNORE,
    REVEIL_COMMANDE,
    REVEIL_SEUL,
    MoteurEcoute,
    accuse_reception,
    generer_variantes,
    seuil_similarite,
)


@pytest.fixture
def moteur(config):
    return MoteurEcoute(config)


def config_nommee(config, **general):
    """Copie de la configuration avec la section general modifiee."""
    donnees = copy.deepcopy(config.data)
    donnees["general"].update(general)
    return Config(donnees)


# --------------------------------------------------------------------------
# Comportement nominal
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,commande_attendue", [
    ("Alma, quelle heure est-il", "quelle heure est-il"),
    ("alma ouvre Chrome", "ouvre Chrome"),
    ("Alma mets le volume à 30%", "mets le volume à 30%"),
    ("ok Alma, prends une capture d'écran", "prends une capture d'écran"),
    ("hey alma raconte-moi une blague", "raconte-moi une blague"),
])
def test_mot_appel_suivi_d_une_commande(moteur, phrase, commande_attendue):
    """« Alma » + commande : elle doit être exécutée directement."""
    analyse = moteur.analyser(phrase)
    assert analyse.etat == REVEIL_COMMANDE
    assert analyse.commande == commande_attendue


@pytest.mark.parametrize("phrase", ["Alma", "alma", "  Alma  ", "ok alma", "Alma euh"])
def test_mot_appel_seul_arme_l_assistant(moteur, phrase):
    """« Alma » seul : accusé de réception, puis l'assistant reste réceptif."""
    analyse = moteur.analyser(phrase)
    assert analyse.etat == REVEIL_SEUL
    assert analyse.commande == ""
    assert moteur.arme is True


def test_commande_acceptee_apres_un_reveil_seul(moteur):
    moteur.analyser("Alma")
    analyse = moteur.analyser("quelle heure est-il")
    assert analyse.etat == COMMANDE
    assert analyse.commande == "quelle heure est-il"


def test_l_armement_se_consomme(moteur):
    """Une seule commande par réveil : ensuite il faut redire le nom."""
    moteur.analyser("Alma")
    moteur.analyser("quelle heure est-il")
    assert moteur.arme is False
    assert moteur.analyser("ouvre Chrome").etat == IGNORE


def test_l_armement_expire(config):
    moteur = MoteurEcoute(config, duree_armement=0.0)
    moteur.analyser("Alma")
    assert moteur.arme is False
    assert moteur.analyser("quelle heure est-il").etat == IGNORE


@pytest.mark.parametrize("phrase", [
    "quelle heure est-il",
    "je parle à quelqu un d autre",
    "il fait beau aujourd hui",
    "",
])
def test_conversation_ambiante_ignoree(moteur, phrase):
    """Sans son nom, l'assistant reste passif : pas de déclenchement accidentel."""
    assert moteur.analyser(phrase).etat == IGNORE


def test_separer_mot_appel_preserve_accents_et_casse(moteur):
    present, reste = moteur.separer_mot_appel("Alma, cherche des idées de repas sur Google")
    assert present is True
    assert reste == "cherche des idées de repas sur Google"


# --------------------------------------------------------------------------
# Seuil adapte a la longueur du nom
# --------------------------------------------------------------------------
def test_le_seuil_est_plus_strict_pour_les_noms_courts():
    """
    Un nom de 4 lettres partage mécaniquement 3 lettres sur 4 avec des
    dizaines de mots : il faut exiger une correspondance exacte.
    """
    assert seuil_similarite("alma") == 1.0
    assert seuil_similarite("vesna") < 1.0
    assert seuil_similarite("assistant") < seuil_similarite("vesna")


@pytest.mark.parametrize("mot_proche", ["alba", "ala", "arme", "ame", "alpha", "elsa"])
def test_les_mots_proches_ne_reveillent_pas(moteur, mot_proche):
    """« Alba » ne doit jamais réveiller « Alma »."""
    moteur.desarmer()
    assert moteur.analyser(mot_proche).etat == IGNORE, mot_proche


@pytest.mark.parametrize("variante", ["alma", "almat", "almas", "halma"])
def test_variantes_de_transcription_reconnues(moteur, variante):
    """La transcription ajoute souvent une finale muette ou un h initial."""
    moteur.desarmer()
    assert moteur.analyser(variante).etat == REVEIL_SEUL, variante


def test_variantes_generees_contiennent_le_mot_lui_meme():
    variantes = generer_variantes("Alma")
    assert "alma" in variantes
    assert all(v == v.lower() for v in variantes)


# --------------------------------------------------------------------------
# Le nom vient entierement de la configuration
# --------------------------------------------------------------------------
def test_renommer_l_assistant_ne_demande_aucun_code(config):
    """Changer general.wake_word doit suffire à renommer l'assistant."""
    moteur = MoteurEcoute(config_nommee(config, wake_word="vesna"))
    assert moteur.analyser("Vesna, quelle heure est-il").etat == REVEIL_COMMANDE
    moteur.desarmer()
    # L ancien nom ne doit plus rien declencher.
    assert moteur.analyser("Alma, quelle heure est-il").etat == IGNORE


def test_variantes_supplementaires_depuis_la_configuration(config):
    """L'utilisateur peut ajouter une transcription qu'il constate."""
    moteur = MoteurEcoute(config_nommee(config, wake_variants=["alpha"]))
    assert moteur.analyser("alpha").etat == REVEIL_SEUL


def test_prefixe_obligatoire(config):
    """
    Option pour les noms proches d'un mot courant : le nom seul ne suffit
    plus, il faut « OK Alma ».
    """
    moteur = MoteurEcoute(config_nommee(config, wake_require_prefix=True))
    assert moteur.analyser("Alma").etat == IGNORE
    assert moteur.analyser("ok Alma").etat == REVEIL_SEUL


def test_les_repliques_sont_prechauffees():
    """Chaque accusé de réception doit être pré-synthétisé pour rester instantané."""
    from core.tts import PHRASES_PRECHAUFFEES

    for replique in ACCUSES:
        assert replique in PHRASES_PRECHAUFFEES, replique + " n est pas pre-synthetise"


def test_accuse_de_reception_est_une_replique_connue():
    for _ in range(20):
        assert accuse_reception() in ACCUSES


@pytest.mark.parametrize("phrase,commande", [
    ("salut Alma", "salut"),
    ("bonjour Alma", "bonjour"),
])
def test_une_salutation_adressee_a_l_assistant_reste_une_salutation(moteur, phrase, commande):
    """
    « Salut » est une salutation, pas un préfixe technique comme « ok ».
    Elle doit être transmise comme commande pour déclencher une réponse,
    et non avalée avec le nom.
    """
    moteur.desarmer()
    analyse = moteur.analyser(phrase)
    assert analyse.etat == REVEIL_COMMANDE
    assert analyse.commande == commande


def test_les_prefixes_techniques_sont_jetes(moteur):
    """« ok » et « dis » n'ont pas de sens comme commande : on les retire."""
    for prefixe in ("ok", "dis", "hey"):
        moteur.desarmer()
        assert moteur.analyser(prefixe + " Alma").etat == REVEIL_SEUL
