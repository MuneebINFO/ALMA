"""
ALMA comprend le français ET l'anglais -- le README le promet, et jusqu'à
présent seule une partie des commandes le tenaient vraiment. Ce fichier
verrouille la couverture anglaise, module par module, à mesure qu'elle est
ajoutée : une phrase anglaise ici doit router vers EXACTEMENT la même
commande que son équivalent français.

Règle pour la suite : toute commande nouvelle doit avoir sa formulation
anglaise dès sa création, pas ajoutée après coup -- voir CONTRIBUTING.md.
"""

import pytest

from core.context import Utterance


def route(router, phrase):
    utterance = Utterance.parse(phrase, wake_words=["alma"])
    resolution = router.resolve(utterance, None)
    return resolution.command.name if resolution else "aucune"


# --------------------------------------------------------------------------
# commands/fenetres.py -- onglets, fenêtres, écrans
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("close tab 3", "fermer_onglet_numero"),
    ("close tab number 3", "fermer_onglet_numero"),
    ("close the third tab", "fermer_onglet_numero"),
    ("close the last tab", "fermer_onglet_numero"),
    ("new tab", "nouvel_onglet"),
    ("open a new tab", "nouvel_onglet"),
    ("close this tab", "fermer_onglet"),
    ("close the page", "fermer_onglet"),
    ("reopen the closed tab", "rouvrir_onglet"),
    ("next tab", "onglet_suivant"),
    ("previous tab", "onglet_precedent"),
    ("refresh the page", "rafraichir"),
    ("reload", "rafraichir"),
    ("previous page", "page_precedente"),
    ("go back", "page_precedente"),
    ("next page", "page_suivante"),
    ("go forward", "page_suivante"),
    ("zoom in", "zoom_avant"),
    ("too small", "zoom_avant"),
    ("zoom out", "zoom_arriere"),
    ("too big", "zoom_arriere"),
    ("reset zoom", "zoom_normal"),
    ("full screen", "plein_ecran"),
    ("go full screen", "plein_ecran"),
    ("minimize the window", "minimiser"),
    ("minimize", "minimiser"),
    ("maximize the window", "agrandir_fenetre"),
    ("close this window", "fermer_fenetre"),
    ("switch window", "changer_fenetre"),
    ("next window", "changer_fenetre"),
    ("show desktop", "afficher_bureau"),
    ("capture a region", "capture_zone"),
    ("grab a region", "capture_zone"),
    ("switch to screen 2", "choisir_ecran"),
    ("go to monitor 1", "choisir_ecran"),
    ("screen 1", "choisir_ecran"),
    ("the second screen", "choisir_ecran"),
    ("which screen are you on", "quel_ecran"),
])
def test_fenetres_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/apps.py -- ouvrir, fermer, aller sur une application
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("open Chrome", "open_app"),
    ("launch Chrome", "open_app"),
    ("start the calculator", "open_app"),
    ("close Chrome", "close_app"),
    ("kill Chrome", "close_app"),
    ("close all Chrome", "close_app"),
    ("switch to Chrome", "aller_sur_application"),
    ("go to Spotify", "aller_sur_application"),
    ("show Spotify", "aller_sur_application"),
    ("list apps", "list_apps"),
])
def test_apps_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/media.py -- lecture, pause, musique
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("pause the video on screen 2", "media_pause_ecran"),
    ("resume playback on screen 2", "media_reprise_ecran"),
    ("pause everything", "media_pause_tout"),
    ("what's playing", "media_what_is_playing"),
    ("play", "media_play_pause"),
    ("pause", "media_play_pause"),
    ("next song", "media_next"),
    ("skip", "media_next"),
    ("previous song", "media_previous"),
    ("play some music", "play_music"),
    ("play the video", "media_lecture"),
    ("pause the video", "media_mettre_en_pause"),
    ("stop the music", "media_mettre_en_pause"),
])
def test_media_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/websites.py -- sites web, recherche, titres
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("open YouTube", "open_website"),
    ("go to YouTube", "open_website"),
    ("switch to Netflix", "open_website"),
    ("open example.com", "open_raw_url"),
    ("list websites", "list_websites"),
    ("open YouTube in a new tab", "ouvrir_site_nouvel_onglet"),
    ("go home", "retour_accueil"),
    ("play Fast and Furious on Netflix", "site_search"),
    ("watch the show The Flash", "lancer_titre"),
    ("play the movie Interstellar on Netflix", "lancer_titre"),
])
def test_websites_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/system.py -- volume, luminosité, session, dossiers
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("set the video volume to 30", "volume_media_set"),
    ("turn up the video volume", "volume_media_up"),
    ("turn down the video volume", "volume_media_down"),
    ("set the volume to 70", "volume_set"),
    ("turn up the volume", "volume_up"),
    ("louder", "volume_up"),
    ("turn down the volume", "volume_down"),
    ("quieter", "volume_down"),
    ("mute", "volume_mute"),
    ("unmute", "volume_unmute"),
    ("what's the volume", "volume_status"),
    ("set the brightness to 50", "brightness_set"),
    ("increase the brightness", "brightness_change"),
    ("decrease the brightness", "brightness_change"),
    ("take a screenshot", "screenshot"),
    ("lock the computer", "lock_session"),
    ("put the computer to sleep", "sleep_pc"),
    ("shut down the computer", "shutdown_pc"),
    ("restart the computer", "restart_pc"),
    ("cancel the shutdown", "abort_shutdown"),
    ("open my downloads", "open_folder"),
    ("open the folder Documents", "open_folder"),
])
def test_system_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/interaction.py -- défilement et clic
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("scroll down", "defiler"),
    ("scroll up", "defiler"),
    ("click on the first video", "cliquer_ordinal"),
    ("open the last result", "cliquer_ordinal"),
    ("click on Subscribe", "cliquer_sur"),
    ("click the play button", "cliquer_sur"),
])
def test_interaction_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/clavier.py -- copier, coller, annuler...
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("copy", "copier"),
    ("paste", "coller"),
    ("cut", "couper_selection"),
    ("undo", "annuler"),
    ("redo", "refaire"),
    ("select all", "tout_selectionner"),
    ("save", "enregistrer"),
    ("print", "imprimer"),
    ("search in page", "rechercher_dans_page"),
    ("write hello world", "dicter"),
    ("confirm", "valider"),
    ("escape", "echapper"),
])
def test_clavier_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


# --------------------------------------------------------------------------
# commands/calcul.py -- calcul, hasard
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("how much is 15 times 4", "calculer"),
    ("what is 15 plus 4", "calculer"),
    ("calculate 15 minus 4", "calculer"),
    ("flip a coin", "pile_ou_face"),
    ("roll a die", "lancer_de"),
    ("random number between 1 and 100", "nombre_aleatoire"),
])
def test_calcul_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


@pytest.mark.parametrize("phrase,attendu", [
    ("clear history", "clear_history"),
])
def test_misc_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


@pytest.mark.parametrize("phrase,attendu", [
    ("battery level", "batterie"),
    ("free disk space", "espace_disque"),
    ("what's my ip address", "adresse_ip"),
    ("empty the recycle bin", "vider_corbeille"),
])
def test_infos_systeme_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


@pytest.mark.parametrize("phrase,attendu", [
    ("who is Marie Curie", "search_wikipedia"),
    ("where is the Eiffel Tower", "search_maps"),
    ("directions to Paris", "search_maps"),
    ("search images of mountains", "search_images"),
    ("show me photos of cats", "search_images"),
])
def test_search_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


@pytest.mark.parametrize("phrase,attendu", [
    ("note that I need to call my bank tomorrow", "add_note"),
    ("read my notes", "read_notes"),
    ("delete note 2", "delete_note"),
    ("clear all my notes", "clear_notes"),
    ("remind me in 10 minutes to take out the cake", "set_reminder"),
    ("start a timer for 5 minutes", "set_timer"),
    ("my reminders", "list_reminders"),
    ("cancel all my reminders", "cancel_reminders"),
    ("read the clipboard", "read_clipboard"),
    ("copy hello world to the clipboard", "write_clipboard"),
])
def test_productivity_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


def test_duree_en_anglais_est_comprise():
    from core import text_utils
    from core.scheduler import parse_duration
    from datetime import timedelta

    tokens = text_utils.tokenize(text_utils.normalize("in 10 minutes"))
    assert parse_duration(tokens) == timedelta(minutes=10)
    tokens = text_utils.tokenize(text_utils.normalize("in 2 hours"))
    assert parse_duration(tokens) == timedelta(hours=2)


@pytest.mark.parametrize("phrase,attendu", [
    ("remember that I'm allergic to peanuts", "memoire_retenir"),
    ("what do you know about me", "memoire_rappeler"),
    ("my memories", "memoire_rappeler"),
    ("forget that I'm allergic to peanuts", "memoire_oublier"),
    ("forget everything", "memoire_oublier"),
])
def test_memoire_en_anglais(router, phrase, attendu):
    assert route(router, phrase) == attendu, phrase


@pytest.mark.parametrize("phrase,attendu,groupe,valeur", [
    ("ask Claude how a search engine works", "claude_demander",
     "question", "how a search engine works"),
    ("ask Claude Code to list the files in the folder", "claude_code_tache",
     "tache", "list the files in the folder"),
    ("ask Cowork to summarize my notes from this week", "claude_cowork",
     "tache", "summarize my notes from this week"),
    ("go to Cowork", "claude_section", "section", "cowork"),
    ("new session", "claude_section", "section", "new"),
    ("new chat", "claude_section", "section", "new"),
])
def test_claude_en_anglais(phrase, attendu, groupe, valeur):
    """
    Ces commandes exigent l'application Claude ouverte (guard) : on
    verrouille donc directement le motif regex et l'extraction, comme le
    fait deja le reste de la suite pour ce fichier, plutot que de rejouer
    tout le routage.
    """
    from core.registry import load_commands, all_commands
    from core.context import Utterance

    load_commands()
    cmd = next(c for c in all_commands() if c.name == attendu)
    u = Utterance.parse(phrase, wake_words=["alma"])
    trouve = next((m for m in (p.search(u.norm) for p in cmd.patterns) if m), None)
    assert trouve is not None, phrase
    assert trouve.group(groupe).strip().lower() == valeur


def test_calcul_en_anglais_donne_le_bon_resultat():
    from commands.calcul import en_expression, evaluer

    assert evaluer(en_expression("how much is 15 times 4")) == 60
    assert evaluer(en_expression("15 divided by 3")) == 5.0
