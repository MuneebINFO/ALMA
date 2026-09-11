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
