"""
Cliquer dans la PAGE, et ouvrir un site dans un nouvel onglet.

Deux défauts constatés à l'usage :

  - « clique sur Tik Tok » cliquait sur l'ONGLET du navigateur intitulé
    « Tik Tok - Recherche Google », au lieu du résultat dans la page ;
  - « ouvre Google » reprenait cet onglet de résultats — qui porte le nom de
    Google sans être Google — et rien ne semblait se passer.
"""

import pytest

from commands import websites
from core import desktop, interaction
from core.context import Utterance

# Rectangle de la page, releve sur la machine de reference : la barre
# d onglets est au-dessus, a y = -1350.
PAGE = (9, -1199, 2409, -60)


def cible(nom, rect, type_controle=interaction.LIEN):
    return interaction.Cible(nom, rect, object(), type_controle)


# --------------------------------------------------------------------------
# Ce qui appartient a la page
# --------------------------------------------------------------------------
@pytest.mark.parametrize("rect,dedans", [
    ((100, -1100, 410, -1009), True),        # un résultat
    ((9, -1199, 2409, -60), True),           # la page entière
    # L'onglet du navigateur, bien au-dessus de la page.
    ((242, -1350, 333, -1320), False),
    # Le volet qui couvre toute la fenêtre : son centre tombe dans la page,
    # mais il déborde sur la barre d'onglets. C'est lui qui était cliqué.
    ((9, -1350, 2409, -60), False),
    # La barre d'adresse.
    ((300, -1292, 1800, -1262), False),
])
def test_seul_le_contenu_de_la_page_est_retenu(rect, dedans):
    assert interaction._dans(rect, PAGE) is dedans


def test_la_zone_de_page_est_ignoree_hors_navigateur(monkeypatch):
    from core import browser_tabs

    monkeypatch.setattr(browser_tabs, "_client", lambda: (None, None))
    assert interaction.zone_page(object()) is None


# --------------------------------------------------------------------------
# Ce qui est choisi dans la page
# --------------------------------------------------------------------------
def page_de_resultats():
    """Une page de résultats Google, dans l'ordre de lecture."""
    return [
        cible("Utiliser la recherche vocale", (100, -1150, 400, -1120),
              interaction.BOUTON),
        cible("TikTok - Make Your Day TikTok https://www.tiktok.com",
              (100, -1100, 410, -1009)),
        cible("TikTok Login", (100, -1000, 225, -971)),
        cible("Official TikTok", (100, -960, 243, -931)),
        cible("TikTok - Videos, Shop & LIVE – Applications sur Google Play",
              (100, -900, 851, -807)),
    ]


def test_le_premier_resultat_lemporte_sur_le_plus_court():
    """
    « TikTok Login » est plus court, mais c'est le premier résultat que l'on
    veut. Sur une correspondance approchante, l'ordre de lecture renseigne
    mieux que la longueur.
    """
    trouve = interaction.chercher_cible(page_de_resultats(), "Tik Tok")
    assert trouve is not None
    assert trouve.nom.startswith("TikTok - Make Your Day")


def test_la_voix_separe_ce_que_la_page_ecrit_colle():
    """« Tik Tok » à l'oral, « TikTok » à l'écrit."""
    cibles = [cible("TikTok", (0, 0, 200, 40))]
    assert interaction.chercher_cible(cibles, "Tik Tok") is not None
    assert interaction.chercher_cible(cibles, "tiktok") is not None


def test_un_libelle_exact_reste_prioritaire_sur_lordre():
    """La règle d'avant tient : « Damso » vise « Damso », pas le premier venu."""
    cibles = [
        cible("Damso officiel - toutes les vidéos", (0, 0, 400, 40)),
        cible("Damso", (0, 50, 100, 90)),
    ]
    assert interaction.chercher_cible(cibles, "Damso").nom == "Damso"


# --------------------------------------------------------------------------
# « ouvre X » contre « va sur X »
# --------------------------------------------------------------------------
@pytest.fixture
def navigateur(monkeypatch):
    """Observe ce que la commande demande, sans rien ouvrir."""
    etat = {"onglets": [], "affichages": []}
    monkeypatch.setattr(websites, "_nouvel_onglet",
                        lambda ctx, url: etat["onglets"].append(url) or True)
    monkeypatch.setattr(websites, "afficher_site",
                        lambda *a, **k: etat["affichages"].append(a[2]) or (True, "onglet"))
    return etat


@pytest.mark.parametrize("phrase", ["ouvre Google", "lance Google", "ouvre YouTube"])
def test_ouvrir_un_site_donne_un_nouvel_onglet(assistant, navigateur, phrase):
    reponse = assistant.handle(phrase)
    assert reponse.ok, reponse.text
    assert navigateur["onglets"], phrase + " n'a pas ouvert d'onglet"
    assert navigateur["affichages"] == [], "aucun onglet ne devait être repris"


@pytest.mark.parametrize("phrase", [
    "va sur YouTube", "reviens sur Netflix", "bascule sur Google",
    "affiche l'onglet YouTube",
])
def test_y_aller_reprend_longlet_existant(assistant, navigateur, phrase):
    """
    C'est la demande d'origine : « va sur YouTube » ne doit pas recharger une
    vidéo en cours.
    """
    reponse = assistant.handle(phrase)
    assert reponse.ok, reponse.text
    assert navigateur["affichages"], phrase + " n'a pas repris l'onglet"
    assert navigateur["onglets"] == [], "aucun onglet ne devait être créé"


def test_un_site_inconnu_reste_refuse(assistant, navigateur):
    reponse = assistant.handle("ouvre Machinchose")
    assert not reponse.ok or navigateur["onglets"] == []


# --------------------------------------------------------------------------
# « le premier lien »
# --------------------------------------------------------------------------
@pytest.fixture
def page_visible(monkeypatch):
    """La page de résultats, telle que la commande la verra."""
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=20, titre="Tik Tok - Recherche Google - Google Chrome",
                        processus="chrome.exe", ecran=1),
    ])
    monkeypatch.setattr(interaction, "elements_cliquables",
                        lambda fenetre, taille_min=12, visibles_seulement=True,
                        page_seulement=False: page_de_resultats())
    clics = []
    monkeypatch.setattr(interaction, "cliquer",
                        lambda c, physique=False: clics.append(c.nom) or True)
    return clics


def test_le_premier_lien_nest_pas_un_bouton(assistant, page_visible):
    """
    « Utiliser la recherche vocale » vient avant dans la page, mais ce n'est
    pas un lien : la nature dite doit filtrer.
    """
    reponse = assistant.handle("clique sur le premier lien")
    assert reponse.ok, reponse.text
    assert page_visible == ["TikTok - Make Your Day TikTok https://www.tiktok.com"]


def test_le_deuxieme_lien_suit_lordre_de_lecture(assistant, page_visible):
    reponse = assistant.handle("clique sur le deuxième lien")
    assert reponse.ok, reponse.text
    assert page_visible == ["TikTok Login"]
