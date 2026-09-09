"""
Comprendre ce qui est dit, malgré la transcription.

Deux échecs constatés à l'usage :

  - « ouvre l'application Claude » ouvrait le SITE claude.ai, parce que le mot
    « application » était traité comme un parasite ;
  - « clique sur le profil Rehman Muneeb » ne trouvait rien, la reconnaissance
    vocale ayant rendu « Rayman Monique ».
"""

import pytest

from commands.apps import nature_demandee
from core import deduction, interaction
from core.context import Utterance


def cible(nom):
    return interaction.Cible(nom, (0, 0, 300, 80), object(), interaction.LIEN)


# --------------------------------------------------------------------------
# « l application X » contre « le site X »
# --------------------------------------------------------------------------
@pytest.mark.parametrize("demande,attendu", [
    ("l'application Claude", "app"),
    ("l'appli Discord", "app"),
    ("le logiciel Word", "app"),
    ("le programme Spotify", "app"),
    ("le site Claude", "site"),
    ("la page YouTube", "site"),
    # Sans précision, rien à trancher : ce sont les autres règles qui jouent.
    ("Claude", ""),
    ("Chrome", ""),
    ("", ""),
])
def test_la_phrase_dit_elle_meme_ce_quelle_vise(demande, attendu):
    assert nature_demandee(demande) == attendu


@pytest.mark.parametrize("phrase,attendu", [
    # Le cas signalé : Claude existe des deux côtés.
    ("ouvre l'application Claude", "open_app"),
    ("ouvre le site Claude", "open_website"),
    # Le mot de nature l'emporte sur la règle habituelle.
    ("ouvre l'application Google", "open_app"),
    ("ouvre le site YouTube", "open_website"),
    ("ouvre l'appli Discord", "open_app"),
    ("ouvre le logiciel Word", "open_app"),
    # Sans précision, les règles d'avant tiennent.
    ("ouvre Google", "open_website"),
    ("ouvre Netflix", "open_website"),
    ("ouvre Chrome", "open_app"),
])
def test_le_mot_de_nature_tranche(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == attendu, phrase


# --------------------------------------------------------------------------
# Les noms propres, deformes par la transcription
# --------------------------------------------------------------------------
def profils():
    return [cible("Rehman Muneeb"), cible("Profil de Muneeb"),
            cible("Accueil"), cible("Ma liste"), cible("Films")]


@pytest.mark.parametrize("entendu", [
    "Rehman Muneeb",        # correct
    "Rayman Muneeb",        # un mot faux
    "Rehman Monique",       # l'autre mot faux
    "Rayman Monique",       # les DEUX faux : le cas signalé
    "Raiman Mounib",
])
def test_un_nom_propre_deforme_est_quand_meme_reconnu(entendu):
    """
    « Rehman Muneeb » revient en « Rayman Monique » : 0,59 de ressemblance en
    lettres, clés phonétiques différentes — mais la même ossature de
    consonnes, rmnmnb contre rmnmnk, à 0,83.
    """
    trouve = interaction.chercher_cible(profils(), entendu)
    assert trouve is not None, entendu
    assert trouve.nom == "Rehman Muneeb", entendu


@pytest.mark.parametrize("etranger", [
    "Interstellar", "Netflix", "Sébastien", "Deadpool", "Paramètres",
])
def test_lossature_des_consonnes_ne_rapproche_pas_nimporte_quoi(etranger):
    assert interaction.chercher_cible(profils(), etranger) is None, etranger


@pytest.mark.parametrize("phrase,attendu", [
    ("Films", "Films"),
    ("Accueil", "Accueil"),
    ("Ma liste", "Ma liste"),
])
def test_les_libelles_exacts_restent_prioritaires(phrase, attendu):
    assert interaction.chercher_cible(profils(), phrase).nom == attendu


# --------------------------------------------------------------------------
# L ossature des consonnes, en propre
# --------------------------------------------------------------------------
@pytest.mark.parametrize("texte,attendu", [
    ("Rehman Muneeb", "rmnmnb"),
    ("Rayman Monique", "rmnmnk"),
    ("Interstellar", "ntrstlr"),
    ("Accueil", "kl"),
])
def test_le_squelette_ne_garde_que_les_consonnes(texte, attendu):
    assert deduction.squelette_consonnes(texte) == attendu


@pytest.mark.parametrize("a,b,attendu", [
    ("Rayman Monique", "Rehman Muneeb", True),
    ("Rehman Muneeb", "Rehman Muneeb", True),
    ("Interstellar", "Rehman Muneeb", False),
    ("Netflix", "Rehman Muneeb", False),
    # Trop court : sur trois consonnes, n'importe quoi se ressemble.
    ("Monique", "Muneeb", False),
    ("Ma liste", "Ma piste", False),
    ("", "Rehman Muneeb", False),
])
def test_lossature_ne_parle_que_des_noms_assez_longs(a, b, attendu):
    assert deduction.memes_consonnes(a, b) is attendu
