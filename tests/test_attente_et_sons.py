"""
Savoir que la demande est partie.

Deux retours, pour deux silences différents.

L'un est long : aller chercher sur internet, attendre l'application Claude,
analyser une image. Le silence ne s'y distingue pas d'une panne — on ne sait
pas si la demande a été comprise. ALMA dit donc « je cherche » AVANT de
travailler, et seulement pour ce qui prend vraiment du temps.

L'autre est court : une action réussie ne se commente pas à voix haute — la
commenter ferait perdre du temps et couvrirait ce qu'on regarde. Mais sans
rien, le silence ne se distingue pas non plus d'une commande perdue. D'où
quatre bruitages, dont un pour exactement ce cas.
"""

from pathlib import Path

import pytest

from core import annonces, sons
from core.registry import all_commands, load_commands

RACINE = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------
# Les phrases d'attente
# --------------------------------------------------------------------------
@pytest.mark.parametrize("genre", annonces.GENRES)
def test_chaque_genre_parle_les_deux_langues(genre):
    assert annonces.annonce(genre, "fr")
    assert annonces.annonce(genre, "en")


def test_un_genre_inconnu_ne_dit_rien_et_ne_leve_pas():
    """Une annonce ratée ne doit jamais empêcher la commande de s'exécuter."""
    assert annonces.annonce("inexistant", "fr") == ""


def test_les_annonces_restent_courtes():
    """Elles passent devant une réponse qui arrive : plus longues, elles gênent."""
    for genre in annonces.GENRES:
        for langue in ("fr", "en"):
            for formulation in annonces.ANNONCES[genre][0 if langue == "fr" else 1]:
                assert len(formulation) <= 40, (genre, langue, formulation)


def test_plusieurs_formulations_par_genre():
    """La même phrase à chaque fois se remarque au bout de trois fois."""
    for genre in annonces.GENRES:
        for formulations in annonces.ANNONCES[genre]:
            assert len(formulations) >= 2, genre


def test_l_annonce_part_avant_le_travail(assistant, monkeypatch):
    """
    C'est tout son intérêt. Dite après, elle arriverait avec la réponse.
    """
    ordre = []
    monkeypatch.setattr(assistant, "annoncer_attente",
                        lambda genre, langue="fr": ordre.append("annonce " + genre))

    def faux_resume(query, lang="fr", timeout=8):
        ordre.append("travail")
        return query, "Un résumé."

    from commands import search

    monkeypatch.setattr(search, "_wikipedia_summary", faux_resume)
    assistant.handle("qui est Marie Curie")

    assert ordre == ["annonce recherche", "travail"], ordre


def test_une_commande_immediate_n_annonce_rien(assistant, monkeypatch):
    """Une annonce suivie d'une réponse instantanée est du bruit."""
    dites = []
    monkeypatch.setattr(assistant, "annoncer_attente",
                        lambda genre, langue="fr": dites.append(genre))
    assistant.handle("quelle heure est-il")
    assert dites == []


def test_l_annonce_est_dans_la_langue_de_la_demande(assistant, monkeypatch):
    langues = []
    monkeypatch.setattr(assistant, "annoncer_attente",
                        lambda genre, langue="fr": langues.append(langue))
    from commands import search

    monkeypatch.setattr(search, "_wikipedia_summary",
                        lambda q, lang="fr", timeout=8: (q, "A summary."))
    assistant.handle("who is Marie Curie")
    assert langues == ["en"]


def test_l_annonce_ne_bloque_pas_et_previent_l_interface(assistant):
    """
    Non bloquante, volontairement : la demande doit partir tout de suite.
    Et elle s'affiche, pour qui a coupé la voix.
    """
    vues = []
    assistant.signal_attente = vues.append
    texte = assistant.annoncer_attente("recherche", "fr")
    assert texte and vues == [texte]


def test_seules_les_commandes_lentes_annoncent():
    """
    Le garde-fou : `attente` sur une commande rapide se remarquerait tout de
    suite à l'usage, et personne ne penserait à le retirer.
    """
    load_commands()
    annoncent = {c.name for c in all_commands() if c.attente}
    assert annoncent == {
        "claude_demander",      # attend que l'application Claude réponde
        "claude_code_tache",    # le CLI, jusqu'à deux minutes
        "search_wikipedia",     # deux appels réseau
        "weather",              # géocodage puis prévisions
        "lancer_titre",         # chercher, lire les résultats, cliquer
    }, sorted(annoncent)


def test_chaque_attente_declaree_existe():
    load_commands()
    for commande in all_commands():
        if commande.attente:
            assert commande.attente in annonces.GENRES, commande.name


# --------------------------------------------------------------------------
# Les bruitages
# --------------------------------------------------------------------------
def test_les_quatre_bruitages_sont_livres():
    """Générés par outils/generer_sons.py, et versionnés avec le projet."""
    for nom in sons.NOMS:
        fichier = RACINE / "assets" / "sons" / (nom + ".wav")
        assert fichier.is_file(), fichier
        assert fichier.stat().st_size > 1000, nom


def test_il_y_a_peu_de_bruitages():
    """Un assistant qui tinte à chaque geste devient fatigant en une demi-journée."""
    assert len(sons.NOMS) <= 5


def test_un_bruitage_absent_est_un_silence_pas_une_panne(tmp_path, config):
    boite = sons.Bruitages(config)
    boite._dossier = tmp_path
    assert boite.chemin("reveil") is None
    assert boite.jouer("reveil") is False


def test_les_bruitages_se_coupent_par_la_configuration(config):
    import copy

    from config import Config

    donnees = copy.deepcopy(config.data)
    donnees["sound"]["enabled"] = False
    boite = sons.Bruitages(Config(donnees))
    assert boite.actifs is False
    assert boite.jouer("ok") is False


def test_sans_configuration_ils_sont_actifs():
    assert sons.Bruitages(None).actifs is True


@pytest.mark.parametrize("phrase,attendu", [
    ("coupe les bruitages", False),
    ("plus de bips", False),
    ("turn off the sound effects", False),
    ("mute the sounds", False),
    ("remets les bruitages", True),
    ("turn on the sounds", True),
])
def test_les_bruitages_se_coupent_a_la_voix(assistant, phrase, attendu):
    assistant.handle(phrase)
    assert assistant.config.get("sound.enabled") is attendu


def test_le_reglage_survit_au_redemarrage(assistant):
    from config import load_config

    assistant.handle("coupe les bruitages")
    apres = load_config(preferences_file=assistant.preferences.chemin)
    assert apres.get("sound.enabled") is False


def test_couper_le_son_reste_le_volume(assistant):
    """« coupe le son » touche le volume de Windows, pas les bruitages."""
    from core.context import Utterance

    resolution = assistant.router.resolve(
        Utterance.parse("coupe le son"), assistant=assistant)
    assert resolution.command.name == "volume_mute"


def test_le_bruitage_ne_fait_jamais_echouer_ce_qu_il_accompagne(assistant,
                                                                monkeypatch):
    def casser(self, nom):
        raise OSError("carte son retirée")

    monkeypatch.setattr(sons.Bruitages, "jouer", casser)
    assert assistant.bruit("ok") is False


def test_les_bruitages_sont_embarques_dans_l_executable():
    """
    Oubliés du packaging, ils resteraient dans le dépôt et l'exe serait muet
    — sans rien signaler, puisqu'un fichier absent est un silence et non une
    erreur. C'est exactement le genre de manque qui ne se voit qu'à l'usage.
    """
    import build_exe

    cibles = {source for source, _ in build_exe.DONNEES}
    assert "assets/sons" in cibles, sorted(cibles)
