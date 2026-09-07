"""
Retour à la page d'accueil d'un site.

Le mécanisme est volontairement générique : on lit l'adresse affichée par le
navigateur et on remonte à sa racine. Il marche donc aussi sur les sites qui
ne figurent pas dans la configuration.
"""

import pytest

from core import browser_tabs, desktop
from core.context import Utterance


@pytest.mark.parametrize("adresse,attendu", [
    # Chrome n'affiche pas le protocole.
    ("youtube.com/watch?v=abc&t=1s", "https://youtube.com/"),
    ("netflix.com/watch/80144925?trackId=284616272", "https://netflix.com/"),
    ("disneyplus.com/fr-fr/play/120ae1e6-2240", "https://disneyplus.com/"),
    ("primevideo.com/detail/0KENQDS0HLUR62", "https://primevideo.com/"),
    # Un site inconnu de la configuration marche tout autant.
    ("anime-sama.fr/catalogue/detective-conan", "https://anime-sama.fr/"),
    ("https://www.netflix.com/browse", "https://www.netflix.com/"),
    ("http://exemple.fr/a/b#c", "http://exemple.fr/"),
    ("x.com", "https://x.com/"),
    # Ce qui n'est pas une adresse ne doit rien produire.
    ("météo demain", ""),
    ("", ""),
    ("chrome://settings", ""),
    ("localhost:3000/app", ""),
])
def test_la_racine_du_site_est_deduite_de_ladresse(adresse, attendu):
    assert browser_tabs.racine_du_site(adresse) == attendu


@pytest.mark.parametrize("phrase", [
    "retourne à l'accueil",
    "retour à l'accueil",
    "reviens à l'accueil",
    "ramène-moi à l'accueil",
    "va à l'accueil",
    "accueil",
    "page d'accueil",
    "reviens à la page principale",
    "home",
    "retourne à l'accueil de Netflix",
    "accueil de Disney+",
])
def test_les_formulations_atteignent_la_commande(assistant, phrase):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None, phrase + " n'atteint aucune commande"
    assert resolution.command.name == "retour_accueil", phrase


@pytest.mark.parametrize("phrase,attendu", [
    # Ces phrases-là appartiennent à d'autres commandes.
    ("va sur Netflix", "open_website"),
    ("reviens sur YouTube", "open_website"),
    ("ouvre YouTube", "open_website"),
    ("clique sur Accueil", "cliquer_sur"),
])
def test_les_commandes_voisines_ne_sont_pas_captees(assistant, phrase, attendu):
    resolution = assistant.router.resolve(Utterance.parse(phrase), assistant=assistant)
    assert resolution is not None and resolution.command.name == attendu, phrase


@pytest.fixture
def navigateur(monkeypatch):
    """Une fenêtre de navigateur, dont on observe les navigations."""
    fenetre = desktop.Fenetre(handle=20, titre="Interstellar - Netflix - Google Chrome",
                              processus="chrome.exe", ecran=1)
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [fenetre])
    allees = []
    monkeypatch.setattr(desktop, "naviguer_dans_fenetre",
                        lambda f, url: allees.append((f.handle, url)) or True)
    return allees


def test_on_remonte_a_la_racine_du_site_affiche(assistant, navigateur, monkeypatch):
    monkeypatch.setattr(browser_tabs, "adresse_courante",
                        lambda f: "netflix.com/watch/80144925")
    reponse = assistant.handle("retourne à l'accueil")
    assert reponse.ok, reponse.text
    assert navigateur == [(20, "https://netflix.com/")]


def test_un_site_hors_configuration_marche_aussi(assistant, navigateur, monkeypatch):
    monkeypatch.setattr(browser_tabs, "adresse_courante",
                        lambda f: "anime-sama.fr/catalogue/detective-conan")
    assert assistant.handle("retourne à l'accueil").ok
    assert navigateur == [(20, "https://anime-sama.fr/")]


def test_le_titre_sert_de_repli_quand_ladresse_est_illisible(assistant, navigateur,
                                                             monkeypatch):
    """La barre d'adresse peut être vide ou contenir une recherche."""
    monkeypatch.setattr(browser_tabs, "adresse_courante", lambda f: "")
    reponse = assistant.handle("retourne à l'accueil")
    assert reponse.ok, reponse.text
    assert navigateur and "netflix" in navigateur[0][1]


def test_sans_rien_pour_identifier_le_site_on_le_demande(assistant, navigateur,
                                                         monkeypatch):
    monkeypatch.setattr(desktop, "fenetres", lambda *a, **k: [
        desktop.Fenetre(handle=30, titre="Sans titre - Google Chrome",
                        processus="chrome.exe", ecran=1),
    ])
    monkeypatch.setattr(browser_tabs, "adresse_courante", lambda f: "")
    reponse = assistant.handle("retourne à l'accueil")
    assert not reponse.ok
    assert "Netflix" in reponse.text          # l'exemple proposé
    assert navigateur == []


def test_un_site_inconnu_nest_pas_invente(assistant, navigateur):
    reponse = assistant.handle("retourne à l'accueil de Machinchose")
    assert not reponse.ok
    assert "Machinchose" in reponse.text
    assert navigateur == []


# La normalisation remplace aussi la ponctuation par des espaces : le
# resultat attendu en garde la trace.
@pytest.mark.parametrize("titre,attendu", [
    ("Netflix - Google Chrome", "netflix"),
    ("Interstellar - Netflix - Google Chrome", "interstellar   netflix"),
    ("Sans titre - Google Chrome", "sans titre"),
    ("YouTube — Mozilla Firefox", "youtube"),
    ("Accueil | Disney+ - Microsoft Edge", "accueil   disney"),
    ("Sans navigateur", "sans navigateur"),
])
def test_le_nom_du_navigateur_est_retire_du_titre(titre, attendu):
    """
    Tout titre de fenêtre finit par le nom du navigateur : sans le retirer,
    « Sans titre - Google Chrome » passerait pour une page Google.
    """
    from commands.websites import sans_le_navigateur

    assert sans_le_navigateur(titre) == attendu
