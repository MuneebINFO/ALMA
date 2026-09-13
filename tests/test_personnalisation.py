"""
Ce qu'ALMA retient de vous.

Chaque personnalisation doit faire DEUX choses, et l'une sans l'autre ne
vaut rien : s'appliquer tout de suite — sinon « appelle-toi Jarvis » ne
répondrait au nouveau nom qu'au prochain lancement — et survivre à la
fermeture, sinon elle est oubliée le soir même.

Ce fichier vérifie les deux, pour chaque réglage, dans les deux langues.
"""

import pytest

from config import Config, load_config
from core.context import Utterance
from core.preferences import CATALOGUE, PAR_CHEMIN, Preferences


def route(assistant, phrase):
    utterance = Utterance.parse(phrase, wake_words=["alma"])
    resolution = assistant.router.resolve(utterance, assistant=assistant)
    return resolution.command.name if resolution else "aucune"


def relire(assistant) -> Config:
    """La configuration telle qu'elle serait au prochain lancement."""
    return load_config(preferences_file=assistant.preferences.chemin)


# --------------------------------------------------------------------------
# Le routage, dans les deux langues
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    # Identité
    ("appelle-toi Jarvis", "renommer_assistant"),
    ("change ton nom en Jarvis", "renommer_assistant"),
    ("tu t'appelles Jarvis", "renommer_assistant"),
    ("ton nom est Jarvis", "renommer_assistant"),
    ("je veux t'appeler Jarvis", "renommer_assistant"),
    ("call yourself Jarvis", "renommer_assistant"),
    ("your name is Jarvis", "renommer_assistant"),
    ("change your name to Jarvis", "renommer_assistant"),
    ("appelle-moi Muneeb", "nommer_utilisateur"),
    ("je m'appelle Muneeb", "nommer_utilisateur"),
    ("mon prénom est Muneeb", "nommer_utilisateur"),
    ("tu peux m'appeler Muneeb", "nommer_utilisateur"),
    ("call me Muneeb", "nommer_utilisateur"),
    ("my name is Muneeb", "nommer_utilisateur"),
    # Langue et voix
    ("parle-moi en anglais", "changer_de_langue"),
    ("passe en anglais", "changer_de_langue"),
    ("speak French", "changer_de_langue"),
    ("switch to English", "changer_de_langue"),
    ("ne parle plus", "couper_la_voix"),
    ("arrête de parler", "couper_la_voix"),
    ("mode silencieux", "couper_la_voix"),
    ("stop talking", "couper_la_voix"),
    ("parle à voix haute", "rendre_la_voix"),
    ("remets ta voix", "rendre_la_voix"),
    ("speak out loud", "rendre_la_voix"),
    ("prends une voix d'homme", "changer_de_voix"),
    ("voix de femme", "changer_de_voix"),
    ("use a male voice", "changer_de_voix"),
    ("speak with a female voice", "changer_de_voix"),
    ("parle plus vite", "changer_le_debit"),
    ("parle moins vite", "changer_le_debit"),
    ("parle normalement", "changer_le_debit"),
    ("speak faster", "changer_le_debit"),
    ("speak more slowly", "changer_le_debit"),
    # Comportement
    ("ne me demande plus confirmation", "regler_les_confirmations"),
    ("demande-moi toujours confirmation", "regler_les_confirmations"),
    ("stop asking for confirmation", "regler_les_confirmations"),
    ("always ask for confirmation", "regler_les_confirmations"),
    ("reste éveillé 2 minutes", "regler_duree_ecoute"),
    ("stay awake for 30 seconds", "regler_duree_ecoute"),
    ("sois plus sensible", "regler_sensibilite"),
    ("tu m'entends mal", "regler_sensibilite"),
    ("be more sensitive", "regler_sensibilite"),
    # Contenu
    ("ma ville c'est Bruxelles", "regler_ma_ville"),
    ("j'habite à Paris", "regler_ma_ville"),
    ("my city is Brussels", "regler_ma_ville"),
    ("I live in Brussels", "regler_ma_ville"),
    ("ma musique est dans D:/Musique", "regler_dossier_musique"),
    ("my music is in D:/Music", "regler_dossier_musique"),
    # Revoir et oublier
    ("quelles sont mes préférences", "mes_preferences"),
    ("mes réglages", "mes_preferences"),
    ("what are my preferences", "mes_preferences"),
    ("oublie mes préférences", "oublier_preferences"),
    ("remets les réglages par défaut", "oublier_preferences"),
    ("reset your settings", "oublier_preferences"),
])
def test_chaque_personnalisation_est_comprise(assistant, phrase, attendu):
    assert route(assistant, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# Le nom de l'assistant
# --------------------------------------------------------------------------
def test_renommer_change_le_nom_ET_le_mot_dappel(assistant):
    """
    Un assistant qui s'appelle Jarvis mais ne répond qu'à « Alma » n'a pas
    changé de nom. Les deux vont ensemble.
    """
    assistant.handle("appelle-toi Jarvis")
    assert assistant.name == "Jarvis"
    assert assistant.config.get("general.wake_word") == "jarvis"
    # Le nouveau nom réveille TOUT DE SUITE, sans redémarrer.
    assert assistant.moteur.est_mot_appel("jarvis") is True
    assert assistant.moteur.est_mot_appel("alma") is False


def test_le_nouveau_nom_survit_au_redemarrage(assistant):
    assistant.handle("appelle-toi Jarvis")
    assert relire(assistant).get("general.assistant_name") == "Jarvis"
    assert relire(assistant).get("general.wake_word") == "jarvis"
    # Et les mots d'appel dérivés suivent, sinon une phrase tapée garderait
    # « Alma » en tête.
    assert "jarvis" in relire(assistant).get("general.wake_words")


def test_la_majuscule_est_rendue_au_nom_prononce(assistant):
    """La transcription vocale rend rarement la majuscule."""
    assistant.handle("appelle-toi jarvis")
    assert assistant.name == "Jarvis"


def test_un_nom_trop_court_est_refuse(assistant):
    """Sous trois lettres, il serait confondu avec la moitié du dictionnaire."""
    reponse = assistant.handle("appelle-toi Al")
    assert not reponse.ok
    assert assistant.name == "ALMA"


@pytest.mark.parametrize("question", ["tu t'appelles comment", "je m'appelle comment"])
def test_une_question_ne_renomme_personne(assistant, question):
    """« tu t'appelles comment ? » ne doit pas le baptiser « Comment »."""
    assistant.handle(question)
    assert assistant.name == "ALMA"
    assert assistant.config.get("general.user_name") != "Comment"


def test_on_peut_revenir_en_arriere(assistant):
    assistant.handle("appelle-toi Jarvis")
    assistant.handle("appelle-toi Alma")
    assert assistant.name == "Alma"
    assert assistant.moteur.est_mot_appel("alma") is True


# --------------------------------------------------------------------------
# Le nom de l'utilisateur
# --------------------------------------------------------------------------
def test_le_prenom_est_retenu_et_resservi(assistant):
    from commands.smalltalk import greeting_for_now

    assistant.handle("appelle-moi Muneeb")
    assert assistant.config.get("general.user_name") == "Muneeb"
    assert relire(assistant).get("general.user_name") == "Muneeb"
    assert "Muneeb" in greeting_for_now("Muneeb")


def test_demander_son_propre_nom_le_rappelle(assistant):
    assistant.handle("appelle-moi Muneeb")
    assert "Muneeb" in assistant.handle("je m'appelle comment").text


# --------------------------------------------------------------------------
# Langue et voix
# --------------------------------------------------------------------------
def test_changer_de_langue_emmene_l_ecoute_et_la_voix(assistant):
    """Répondre en anglais avec une voix française ne servirait à rien."""
    assistant.handle("parle-moi en anglais")
    assert assistant.config.get("general.language") == "en"
    assert assistant.config.get("voice.stt_language") == "en-US"
    assert assistant.config.get("voice.neural_voice").startswith("en-")


def test_le_genre_de_la_voix_survit_au_changement_de_langue(assistant):
    assistant.handle("prends une voix d'homme")
    voix_fr = assistant.config.get("voice.neural_voice")
    assistant.handle("parle-moi en anglais")
    voix_en = assistant.config.get("voice.neural_voice")
    from core.preferences import genre_de_la_voix

    assert genre_de_la_voix(voix_fr) == "homme"
    assert genre_de_la_voix(voix_en) == "homme"
    assert voix_fr != voix_en


def test_la_reponse_au_changement_de_langue_est_dans_la_langue_demandee(assistant):
    """C'est la première preuve que le changement a pris."""
    assert "English" in assistant.handle("parle-moi en anglais").text
    assert "français" in assistant.handle("speak French").text


def test_couper_et_rendre_la_voix(assistant):
    assistant.handle("ne parle plus")
    assert assistant.config.get("voice.speak_responses") is False
    assert relire(assistant).get("voice.speak_responses") is False
    assistant.handle("parle à voix haute")
    assert assistant.config.get("voice.speak_responses") is True


def test_le_debit_a_trois_crans(assistant):
    assistant.handle("parle plus vite")
    rapide = assistant.config.get("voice.rate")
    assistant.handle("parle moins vite")
    lent = assistant.config.get("voice.rate")
    assistant.handle("parle normalement")
    normal = assistant.config.get("voice.rate")
    assert lent < normal < rapide


# --------------------------------------------------------------------------
# Comportement
# --------------------------------------------------------------------------
def test_les_confirmations_se_coupent_et_se_remettent(assistant):
    assistant.handle("ne me demande plus confirmation")
    assert assistant.config.get("general.confirm_dangerous_actions") is False
    assistant.handle("demande-moi toujours confirmation")
    assert assistant.config.get("general.confirm_dangerous_actions") is True


def test_couper_les_confirmations_dit_ce_que_ca_implique(assistant):
    """On ne revient pas d'une corbeille vidée : il faut le dire."""
    texte = assistant.handle("ne me demande plus confirmation").text.lower()
    assert "corbeille" in texte or "éteindre" in texte


@pytest.mark.parametrize("phrase,attendu", [
    ("reste éveillé 2 minutes", 120),
    ("reste éveillé 30 secondes", 30),
    ("stay awake for 90 seconds", 90),
])
def test_la_duree_decoute_se_regle(assistant, phrase, attendu):
    """« 2 » veut dire deux minutes ; « 90 », quatre-vingt-dix secondes."""
    assistant.handle(phrase)
    assert assistant.config.get("voice.armed_seconds") == attendu
    # Le moteur d'écoute doit l'appliquer sans redémarrage.
    assert assistant.moteur.duree_armement == attendu


def test_la_sensibilite_monte_et_descend(assistant):
    depart = assistant.config.get("voice.min_threshold")
    assistant.handle("sois plus sensible")
    plus = assistant.config.get("voice.min_threshold")
    assert plus < depart, "« plus sensible » doit ABAISSER le seuil"
    assistant.handle("sois moins sensible")
    assert assistant.config.get("voice.min_threshold") == depart


def test_se_plaindre_de_ne_pas_etre_entendu_rend_plus_sensible(assistant):
    """« tu m'entends mal » ne nomme pas de direction, mais n'en a qu'une."""
    depart = assistant.config.get("voice.min_threshold")
    assistant.handle("tu m'entends mal")
    assert assistant.config.get("voice.min_threshold") < depart


def test_la_sensibilite_a_des_butees(assistant):
    for _ in range(6):
        assistant.handle("sois plus sensible")
    reponse = assistant.handle("sois plus sensible")
    assert not reponse.ok, "arrivé au bout, il faut le dire"


# --------------------------------------------------------------------------
# Contenu
# --------------------------------------------------------------------------
def test_la_ville_sert_a_la_meteo(assistant):
    assistant.handle("j'habite à Toulouse")
    assert assistant.config.get("weather.default_city") == "Toulouse"
    assert relire(assistant).get("weather.default_city") == "Toulouse"


def test_un_dossier_de_musique_inexistant_est_refuse(assistant):
    reponse = assistant.handle("ma musique est dans Z:/nexiste/pas")
    assert not reponse.ok
    assert assistant.config.get("paths.music") == ""


def test_le_chemin_garde_sa_casse_et_ses_separateurs(assistant, tmp_path):
    """La normalisation écrase la ponctuation : le chemin vient du texte brut."""
    dossier = tmp_path / "Ma Musique"
    dossier.mkdir()
    assistant.handle("ma musique est dans " + str(dossier))
    assert assistant.config.get("paths.music") == str(dossier)


# --------------------------------------------------------------------------
# Revoir et oublier
# --------------------------------------------------------------------------
def test_lister_ce_qui_a_ete_retenu(assistant):
    assistant.handle("appelle-moi Muneeb")
    assistant.handle("appelle-toi Jarvis")
    reponse = assistant.handle("quelles sont mes préférences")
    assert reponse.ok
    affiche = "\n".join(assistant.io.written) if hasattr(assistant.io, "written") else ""
    assert "Muneeb" in affiche or "Muneeb" in reponse.text


def test_sans_rien_de_retenu_on_le_dit(assistant):
    assert assistant.handle("mes préférences").ok


def test_tout_oublier_ramene_les_valeurs_dorigine(assistant, monkeypatch):
    monkeypatch.setattr(assistant, "confirm", lambda *a, **k: True)
    assistant.handle("appelle-toi Jarvis")
    assistant.handle("appelle-moi Muneeb")
    assistant.handle("ne parle plus")
    assert assistant.preferences.charger()

    assistant.handle("oublie mes préférences")
    assert assistant.preferences.charger() == {}
    assert assistant.name == "ALMA"
    assert assistant.config.get("voice.speak_responses") is True
    # Et le mot d'appel d'origine répond de nouveau.
    assert assistant.moteur.est_mot_appel("alma") is True


def test_refuser_loubli_ne_touche_a_rien(assistant, monkeypatch):
    monkeypatch.setattr(assistant, "confirm", lambda *a, **k: False)
    assistant.handle("appelle-toi Jarvis")
    assistant.handle("oublie mes préférences")
    assert assistant.name == "Jarvis"


# --------------------------------------------------------------------------
# Le magasin lui-même
# --------------------------------------------------------------------------
def test_seuls_les_reglages_du_catalogue_sont_ecrits(tmp_path):
    """Une commande ne doit pas pouvoir toucher un réglage quelconque."""
    magasin = Preferences(tmp_path / "preferences.json")
    assert magasin.definir("general.user_name", "Muneeb") is True
    assert magasin.definir("ai_fallback.enabled", True) is False
    assert magasin.definir("paths.notes", "n'importe où") is False
    assert magasin.charger() == {"general.user_name": "Muneeb"}


def test_un_fichier_illisible_ne_bloque_pas_le_demarrage(tmp_path):
    """Mieux vaut repartir de rien que refuser de se lancer."""
    chemin = tmp_path / "preferences.json"
    chemin.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    assert Preferences(chemin).charger() == {}


def test_un_reglage_inconnu_dans_le_fichier_est_ignore(tmp_path):
    import json

    chemin = tmp_path / "preferences.json"
    chemin.write_text(json.dumps({
        "general.user_name": "Muneeb",
        "ai_fallback.enabled": True,
    }), encoding="utf-8")
    assert Preferences(chemin).charger() == {"general.user_name": "Muneeb"}


def test_les_preferences_passent_par_dessus_config_yaml(tmp_path):
    """Un ordre récent l'emporte sur un réglage écrit une fois pour toutes."""
    import json

    chemin = tmp_path / "preferences.json"
    chemin.write_text(json.dumps({"general.assistant_name": "Jarvis"}),
                      encoding="utf-8")
    assert load_config(preferences_file=chemin).get("general.assistant_name") == "Jarvis"


def test_chaque_reglage_du_catalogue_a_ses_deux_libelles():
    """La liste sert à répondre, donc dans les deux langues."""
    for reglage in CATALOGUE:
        assert reglage.libelle("fr"), reglage.chemin
        assert reglage.libelle("en"), reglage.chemin
        assert reglage.libelle("en") == reglage.libelle_en
    assert len(PAR_CHEMIN) == len(CATALOGUE), "deux réglages sur le même chemin"
