"""
Tests du défilement et du clic.

Rien n'est réellement piloté : la molette, la souris et l'accessibilité sont
remplacées par des doublures. On vérifie les décisions, pas l'API Windows.
"""

import pytest

from core import desktop, interaction
from core.context import Utterance


def fenetre():
    return desktop.Fenetre(handle=1, titre="Page - Google Chrome",
                           processus="chrome.exe", ecran=1)


def cible(nom, rect=(0, 0, 100, 30)):
    return interaction.Cible(nom, rect, element=None)


def resoudre(router, assistant, phrase):
    utterance = Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words"))
    return router.resolve(utterance, assistant)


# --------------------------------------------------------------------------
# Sens du defilement
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,attendu", [
    ("scrolle", interaction.BAS),
    ("fais défiler", interaction.BAS),
    ("descends", interaction.BAS),
    ("fais défiler vers le haut", interaction.HAUT),
    ("scrolle vers le haut", interaction.HAUT),
    ("remonte la page", interaction.HAUT),
])
def test_le_sens_par_defaut_est_vers_le_bas(assistant, phrase, attendu):
    """Vers le bas sauf mention explicite : c'est le cas neuf fois sur dix."""
    from commands.interaction import direction_demandee
    from core.context import CommandContext

    utterance = Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words"))
    ctx = CommandContext(utterance, assistant)
    assert direction_demandee(ctx) == attendu


# --------------------------------------------------------------------------
# Cycle de vie du defilement
# --------------------------------------------------------------------------
def test_demarrer_puis_arreter(monkeypatch):
    crans = []
    monkeypatch.setattr(interaction, "_molette", lambda n: crans.append(n))
    monkeypatch.setattr(interaction, "position_souris", lambda: (0, 0))
    monkeypatch.setattr(interaction, "deplacer_souris", lambda x, y: None)
    monkeypatch.setattr(interaction, "_rectangle_fenetre", lambda h: (0, 0, 800, 600))
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)

    defilement = interaction.Defilement()
    assert defilement.actif is False
    defilement.demarrer(fenetre(), direction=interaction.BAS, intervalle=0.02)
    import time

    time.sleep(0.2)
    assert defilement.actif is True
    assert crans, "la molette aurait dû être actionnée"
    assert all(c < 0 for c in crans), "vers le bas = crans négatifs"
    assert defilement.arreter() is True
    assert defilement.actif is False
    assert defilement.arreter() is False, "un second arrêt ne fait rien"


def test_le_curseur_est_restaure(monkeypatch):
    """Le défilement déplace le curseur : il doit le remettre où il était."""
    positions = []
    monkeypatch.setattr(interaction, "_molette", lambda n: None)
    monkeypatch.setattr(interaction, "position_souris", lambda: (500, 400))
    monkeypatch.setattr(interaction, "deplacer_souris",
                        lambda x, y: positions.append((x, y)))
    monkeypatch.setattr(interaction, "_rectangle_fenetre", lambda h: (0, 0, 800, 600))
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)

    defilement = interaction.Defilement()
    defilement.demarrer(fenetre(), intervalle=0.02)
    import time

    time.sleep(0.15)
    defilement.arreter()
    assert positions[0] == (400, 300), "curseur amené au centre de la fenêtre"
    assert positions[-1] == (500, 400), "curseur remis à sa place"


# --------------------------------------------------------------------------
# Choix de l element a cliquer
# --------------------------------------------------------------------------
def test_correspondance_exacte_prioritaire():
    cibles = [cible("Damso - Macarena (clip officiel) en concert"), cible("Damso")]
    assert interaction.chercher_cible(cibles, "Damso").nom == "Damso"


def test_a_defaut_la_correspondance_la_plus_courte():
    """« Damso » doit viser le lien le plus précis, pas un titre à rallonge."""
    cibles = [cible("Damso en concert à Bruxelles, reportage complet"), cible("Damso officiel")]
    assert interaction.chercher_cible(cibles, "damso").nom == "Damso officiel"


def test_tolerance_aux_erreurs_de_transcription():
    cibles = [cible("Abonnements"), cible("Historique")]
    assert interaction.chercher_cible(cibles, "abonnement").nom == "Abonnements"


def test_element_absent():
    assert interaction.chercher_cible([cible("Accueil")], "Netflix") is None


@pytest.mark.parametrize("rect,visible", [
    ((10, 10, 200, 60), True),
    ((10, -900, 200, -840), False),     # défilé au-dessus de la fenêtre
    ((2000, 10, 2200, 60), False),      # à droite, hors fenêtre
])
def test_seuls_les_elements_a_l_ecran_sont_retenus(rect, visible):
    """Cliquer sur un élément hors champ taperait à côté."""
    assert interaction._visible_dans(rect, (0, 0, 800, 600)) is visible


# --------------------------------------------------------------------------
# « Arrête » : interrompre plutôt que refermer la session
# --------------------------------------------------------------------------
def test_arreter_ne_se_declenche_que_si_ca_defile(assistant, router):
    """
    Sans défilement en cours, « arrête » ne doit pas être capté par cette
    commande — il garde son sens habituel.
    """
    assert assistant.defilement.actif is False
    resolution = resoudre(router, assistant, "arrête")
    assert resolution is None or resolution.command.name != "arreter_defilement"


def test_arreter_prend_la_main_pendant_un_defilement(assistant, router, monkeypatch):
    monkeypatch.setattr(interaction, "_molette", lambda n: None)
    monkeypatch.setattr(interaction, "position_souris", lambda: (0, 0))
    monkeypatch.setattr(interaction, "deplacer_souris", lambda x, y: None)
    monkeypatch.setattr(interaction, "_rectangle_fenetre", lambda h: (0, 0, 800, 600))
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)

    assistant.defilement.demarrer(fenetre(), intervalle=0.05)
    try:
        resolution = resoudre(router, assistant, "arrête")
        assert resolution is not None
        assert resolution.command.name == "arreter_defilement"
    finally:
        assistant.defilement.arreter()


def test_interrompre_signale_ce_qui_a_ete_arrete(assistant, monkeypatch):
    """
    L'interface s'appuie sur ce retour : « arrête » pendant un défilement doit
    arrêter le défilement, pas refermer la session d'écoute.
    """
    monkeypatch.setattr(interaction, "_molette", lambda n: None)
    monkeypatch.setattr(interaction, "position_souris", lambda: (0, 0))
    monkeypatch.setattr(interaction, "deplacer_souris", lambda x, y: None)
    monkeypatch.setattr(interaction, "_rectangle_fenetre", lambda h: (0, 0, 800, 600))
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)

    assert assistant.interrompre() is False, "rien à interrompre au départ"
    assistant.defilement.demarrer(fenetre(), intervalle=0.05)
    assert assistant.interrompre() is True
    assert assistant.interrompre() is False


@pytest.mark.parametrize("phrase,attendu", [
    ("scrolle", "defiler"),
    ("fais défiler vers le haut", "defiler"),
    ("descends", "defiler"),
    ("clique sur la première vidéo", "cliquer_ordinal"),
    ("clique sur Abonnements", "cliquer_sur"),
    ("sélectionne le premier résultat", "cliquer_ordinal"),
])
def test_routage_des_commandes_d_interaction(assistant, router, phrase, attendu):
    resolution = resoudre(router, assistant, phrase)
    assert resolution is not None, phrase
    assert resolution.command.name == attendu


@pytest.mark.parametrize("phrase,attendu", [
    ("monte le son", "volume_up"),
    ("monte la luminosité", "brightness_change"),
    ("baisse le volume", "volume_down"),
])
def test_les_verbes_ambigus_restent_au_bon_endroit(assistant, router, phrase, attendu):
    """
    « monte » et « descends » servent aussi au volume et à la luminosité :
    le défilement ne doit pas les capturer.
    """
    resolution = resoudre(router, assistant, phrase)
    assert resolution is not None and resolution.command.name == attendu


# --------------------------------------------------------------------------
# Titre et type précisés : « la vidéo Interstellar », « le bouton lecture »
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,type_attendu,titre_attendu", [
    ("clique sur la vidéo Interstellar", "video", "Interstellar"),
    ("clique sur le film Interstellar", "film", "Interstellar"),
    ("clique sur le bouton lecture", "bouton", "lecture"),
    ("appuie sur le bouton pause", "bouton", "pause"),
    ("sélectionne la série Breaking Bad", "serie", "Breaking Bad"),
    ("clique sur Abonnements", "", "Abonnements"),
    ("clique sur l'onglet Musique", "onglet", "Musique"),
])
def test_le_type_est_separe_du_titre(assistant, router, phrase, type_attendu, titre_attendu):
    """« la vidéo Interstellar » doit chercher « Interstellar », pas la phrase entière."""
    resolution = resoudre(router, assistant, phrase)
    assert resolution is not None and resolution.command.name == "cliquer_sur", phrase
    raw = Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words")).raw
    groupes = {}
    for nom in ("type", "label"):
        debut, fin = resolution.match.span(nom)
        groupes[nom] = raw[debut:fin] if debut >= 0 else ""
    # Le motif s'applique au texte normalisé : le groupe capturé revient
    # accentué (« vidéo »), c'est la commande qui le normalise ensuite.
    from core import text_utils

    assert text_utils.normalize(groupes["type"]).strip() == type_attendu
    assert groupes["label"] == titre_attendu


def test_le_type_restreint_la_recherche():
    """« le bouton lecture » ne doit pas viser un titre de vidéo."""
    cibles = [
        interaction.Cible("Lecture d'un film culte", (0, 0, 300, 30), None, interaction.LIEN),
        interaction.Cible("Lecture", (0, 40, 80, 70), None, interaction.BOUTON),
    ]
    trouve = interaction.chercher_cible(cibles, "lecture", types=(interaction.BOUTON,))
    assert trouve.type_controle == interaction.BOUTON


def test_la_recherche_s_elargit_si_le_type_ne_donne_rien():
    """Mieux vaut trouver ailleurs que de répondre bredouille."""
    cibles = [interaction.Cible("Interstellar", (0, 0, 300, 30), None, interaction.LIEN)]
    trouve = interaction.chercher_cible(cibles, "Interstellar", types=(interaction.BOUTON,))
    assert trouve is not None and trouve.nom == "Interstellar"


@pytest.mark.parametrize("demande,nom_reel", [
    ("lecture", "Play"),
    ("pause", "Pause (k)"),
    ("plein écran", "Full screen"),
    ("abonnements", "Subscriptions"),
])
def test_les_libelles_anglais_sont_reconnus(demande, nom_reel):
    """Les interfaces sont souvent en anglais même quand on parle français."""
    from commands.interaction import variantes_libelle

    cibles = [interaction.Cible(nom_reel, (0, 0, 100, 30), None, interaction.BOUTON)]
    trouve = None
    for variante in variantes_libelle(demande):
        trouve = interaction.chercher_cible(cibles, variante)
        if trouve is not None:
            break
    assert trouve is not None, demande + " devrait trouver " + nom_reel
