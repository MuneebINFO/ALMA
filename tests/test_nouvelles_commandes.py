"""
Tests des familles ajoutées : édition, fenêtres, informations machine, calcul.
"""

import pytest

from core.context import Utterance


def resoudre(router, config, phrase):
    utterance = Utterance.parse(phrase, wake_words=config.get("general.wake_words"))
    return router.resolve(utterance, None)


ROUTAGE = [
    # Édition
    ("copie la sélection", "copier"),
    ("colle", "coller"),
    ("coupe la sélection", "couper_selection"),
    ("annule la dernière action", "annuler"),
    ("rétablis", "refaire"),
    ("sélectionne tout", "tout_selectionner"),
    ("enregistre", "enregistrer"),
    ("imprime la page", "imprimer"),
    ("cherche dans la page", "rechercher_dans_page"),
    ("écris bonjour tout le monde", "dicter"),
    ("valide", "valider"),
    # Fenêtres et onglets
    ("ouvre un nouvel onglet", "nouvel_onglet"),
    ("ferme cet onglet", "fermer_onglet"),
    ("rouvre l'onglet fermé", "rouvrir_onglet"),
    ("onglet suivant", "onglet_suivant"),
    ("onglet précédent", "onglet_precedent"),
    ("actualise la page", "rafraichir"),
    ("page précédente", "page_precedente"),
    ("zoom avant", "zoom_avant"),
    ("zoom arrière", "zoom_arriere"),
    ("zoom normal", "zoom_normal"),
    ("plein écran", "plein_ecran"),
    ("minimise la fenêtre", "minimiser"),
    ("agrandis la fenêtre", "agrandir_fenetre"),
    ("change de fenêtre", "changer_fenetre"),
    ("affiche le bureau", "afficher_bureau"),
    ("capture une zone", "capture_zone"),
    # Informations machine
    ("niveau de batterie", "batterie"),
    ("espace libre sur le disque", "espace_disque"),
    ("mon adresse IP", "adresse_ip"),
    ("vide la corbeille", "vider_corbeille"),
    # Calcul et hasard
    ("combien font 15 fois 4", "calculer"),
    ("calcule 200 divisé par 8", "calculer"),
    ("pile ou face", "pile_ou_face"),
    ("lance un dé", "lancer_de"),
    ("donne-moi un nombre entre 1 et 100", "nombre_aleatoire"),
]


@pytest.mark.parametrize("phrase,attendu", ROUTAGE)
def test_les_nouvelles_commandes_sont_routees(router, config, phrase, attendu):
    resolution = resoudre(router, config, phrase)
    assert resolution is not None, "aucune commande pour : " + phrase
    assert resolution.command.name == attendu


# Formulations proches qui doivent garder leur destination d'origine.
VOISINS = [
    ("coupe le son", "volume_mute"),           # pas « couper la sélection »
    ("balance de la musique", "play_music"),   # contient « lance de » par hasard
    ("lance la vidéo", "media_lecture"),
    ("ferme Chrome", "close_app"),             # pas « ferme la fenêtre »
    ("ouvre YouTube", "open_website"),         # pas « ouvre un onglet »
    ("prends une capture d'écran", "screenshot"),   # pas « capture une zone »
    ("quelle heure est-il", "get_time"),
]


@pytest.mark.parametrize("phrase,attendu", VOISINS)
def test_les_commandes_existantes_ne_sont_pas_capturees(router, config, phrase, attendu):
    resolution = resoudre(router, config, phrase)
    assert resolution is not None, phrase
    assert resolution.command.name == attendu


# --------------------------------------------------------------------------
# Calcul : exécution réelle
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("combien font 15 fois 4", "60"),
    ("calcule 200 divisé par 8", "25"),
    ("combien font 12 plus 30 moins 5", "37"),
    ("combien font 7 fois 7", "49"),
    ("calcule 10 sur 4", "2.5"),
])
def test_le_calcul_donne_le_bon_resultat(assistant, phrase, attendu):
    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " -> " + reponse.text
    assert attendu in reponse.text


def test_le_calcul_refuse_ce_qui_nest_pas_une_operation(assistant):
    reponse = assistant.handle("calcule bonjour tout le monde")
    assert not reponse.ok


def test_aucun_code_nest_execute():
    """
    L'évaluation n'accepte que des nombres et des opérations : ni appel de
    fonction, ni nom de variable, même si la phrase en contenait.
    """
    from commands.calcul import evaluer

    for tentative in ("__import__('os').system('echo')", "open('x')", "abs(-3)", "x + 1"):
        assert evaluer(tentative) is None, tentative
    assert evaluer("2 + 3 * 4") == 14


def test_les_tirages_restent_dans_les_bornes(assistant):
    for _ in range(20):
        reponse = assistant.handle("donne-moi un nombre entre 1 et 6")
        valeur = int("".join(c for c in reponse.text if c.isdigit()))
        assert 1 <= valeur <= 6
