"""
Tests de l'ouverture de sites avec réutilisation d'onglet et recherche interne.

Aucun navigateur n'est réellement piloté : les appels système sont doublés.
"""

import pytest

from core import desktop
from core.context import Utterance
from core.registry import find
from commands import websites


def executer(router, assistant, phrase):
    """Route puis exécute une phrase, comme le ferait l'assistant."""
    utterance = Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words"))
    return router.run(utterance, assistant)


@pytest.fixture
def sans_navigateur(monkeypatch):
    """
    Aucun site n'est ouvert : tout doit passer par une ouverture classique.
    On neutralise aussi la lecture des onglets, sinon le résultat dépendrait
    de ce qui est réellement ouvert sur la machine de test.
    """
    from core import browser_tabs

    monkeypatch.setattr(browser_tabs, "trouver_onglet", lambda *a, **k: None)
    monkeypatch.setattr(desktop, "trouver_fenetre", lambda *a, **k: None)
    ouvertes = []
    monkeypatch.setattr(websites, "open_url", lambda url: ouvertes.append(url) or True)
    return ouvertes


def test_recherche_dans_un_site(assistant, router, sans_navigateur):
    reponse, _ = executer(router, assistant, "va sur Netflix et mets Fast and Furious")
    assert reponse.ok
    assert len(sans_navigateur) == 1
    url = sans_navigateur[0]
    assert "netflix.com/search" in url
    assert "Fast" in url and "Furious" in url


def test_forme_inversee(assistant, router, sans_navigateur):
    """« mets X sur Y » doit être compris comme « va sur Y et mets X »."""
    reponse, _ = executer(router, assistant, "mets Interstellar sur Prime Video")
    assert reponse.ok
    assert "primevideo.com" in sans_navigateur[0]
    assert "Interstellar" in sans_navigateur[0]


def test_la_requete_nest_pas_tronquee(assistant, router, sans_navigateur):
    """
    « cherche A sur B sur Google » doit couper au DERNIER « sur », sinon la
    requête perd sa fin.
    """
    executer(router, assistant, "cherche les dernières nouvelles sur l'IA sur Google")
    url = sans_navigateur[0]
    assert "google.com/search" in url
    assert "nouvelles" in url and "IA" in url


def test_onglet_existant_reutilise(assistant, router, monkeypatch):
    """
    Si le site est déjà l'onglet actif d'une fenêtre, on doit reprendre cette
    fenêtre plutôt que d'en ouvrir une nouvelle.
    """
    from core import browser_tabs

    fenetre = desktop.Fenetre(handle=7, titre="Netflix - Google Chrome",
                              processus="chrome.exe", ecran=1)
    # Aucun onglet detecte : on force le repli sur le titre de fenetre.
    monkeypatch.setattr(browser_tabs, "trouver_onglet", lambda *a, **k: None)
    monkeypatch.setattr(desktop, "trouver_fenetre", lambda *a, **k: fenetre)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)
    naviguees = []
    monkeypatch.setattr(desktop, "naviguer_dans_fenetre",
                        lambda f, url: naviguees.append((f.handle, url)) or True)
    monkeypatch.setattr(websites, "open_url",
                        lambda url: pytest.fail("un nouvel onglet ne devait pas être ouvert"))

    reponse, _ = executer(router, assistant, "va sur Netflix et mets Fast and Furious")
    assert reponse.ok
    assert naviguees and naviguees[0][0] == 7
    assert "netflix.com/search" in naviguees[0][1]
    assert "reprends" in reponse.text.lower()


def test_wikipedia_reste_traite_par_sa_commande_dediee(router, config):
    """
    La commande Wikipedia lit un résumé à voix haute : site_search ne doit pas
    l'intercepter, ce serait une régression.
    """
    utterance = Utterance.parse("cherche Alan Turing sur Wikipedia",
                                wake_words=config.get("general.wake_words"))
    assert router.resolve(utterance, None).command.name == "search_wikipedia"


def test_site_inconnu_nest_pas_capture(router, config):
    """Un mot qui n'est pas un site connu ne doit pas déclencher site_search."""
    utterance = Utterance.parse("mets la table sur la terrasse",
                                wake_words=config.get("general.wake_words"))
    resolution = router.resolve(utterance, None)
    assert resolution is None or resolution.command.name != "site_search"


def test_beaucoup_de_sites_ont_une_recherche_interne(config):
    """La fonctionnalité doit couvrir un large éventail de plateformes."""
    sites = config.get("websites", {})
    avec_recherche = [c for c, e in sites.items() if isinstance(e, dict) and e.get("search_url")]
    assert len(avec_recherche) >= 25
    for attendu in ("netflix", "youtube", "primevideo", "disney", "spotifyweb", "twitch"):
        assert attendu in avec_recherche, attendu + " devrait supporter la recherche"


# --------------------------------------------------------------------------
# Onglets en arriere-plan
# --------------------------------------------------------------------------
class OngletFactice:
    """Double d'un onglet : mémorise s'il a été activé."""

    def __init__(self, nom, fenetre):
        self.nom = nom
        self.fenetre = fenetre
        self.active = False

    def activer(self):
        self.active = True
        return True


@pytest.fixture
def onglet_youtube(monkeypatch):
    """Un onglet YouTube existe, mais en arrière-plan (titre de fenêtre = TikTok)."""
    from core import browser_tabs

    fenetre = desktop.Fenetre(handle=5, titre="TikTok - Google Chrome",
                              processus="chrome.exe", ecran=1)
    onglet = OngletFactice("YouTube - une vidéo", fenetre)
    monkeypatch.setattr(browser_tabs, "trouver_onglet", lambda *a, **k: onglet)
    monkeypatch.setattr(desktop, "trouver_fenetre", lambda *a, **k: None)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", lambda h: True)
    return onglet


def test_onglet_en_arriere_plan_est_active(assistant, router, onglet_youtube, monkeypatch):
    """
    Le cas qui échouait : YouTube ouvert dans un onglet d'arrière-plan n'était
    pas vu, car Windows n'expose que le titre de l'onglet actif.
    """
    monkeypatch.setattr(websites, "open_url",
                        lambda url: pytest.fail("aucun onglet ne devait être ouvert"))
    reponse, _ = executer(router, assistant, "va sur l'onglet YouTube")
    assert reponse.ok
    assert onglet_youtube.active is True
    assert "onglet" in reponse.text.lower()


def test_afficher_un_site_ne_recharge_pas_la_page(assistant, router, onglet_youtube, monkeypatch):
    """
    « va sur YouTube » doit seulement AFFICHER l'onglet. Y naviguer
    rechargerait l'accueil et couperait la vidéo en cours.
    """
    monkeypatch.setattr(desktop, "naviguer_dans_fenetre",
                        lambda f, url: pytest.fail("la page ne devait pas être rechargée"))
    monkeypatch.setattr(websites, "open_url", lambda url: True)
    reponse, _ = executer(router, assistant, "va sur YouTube")
    assert reponse.ok


def test_recherche_active_l_onglet_puis_navigue(assistant, router, onglet_youtube, monkeypatch):
    """Avec une requête, en revanche, il faut bien charger la recherche."""
    naviguees = []
    monkeypatch.setattr(desktop, "naviguer_dans_fenetre",
                        lambda f, url: naviguees.append(url) or True)
    monkeypatch.setattr(websites, "open_url",
                        lambda url: pytest.fail("un nouvel onglet ne devait pas être ouvert"))
    reponse, _ = executer(router, assistant, "mets lofi hip hop sur YouTube")
    assert reponse.ok
    assert onglet_youtube.active is True
    assert naviguees and "youtube.com/results" in naviguees[0]


def test_sans_onglet_existant_on_ouvre(assistant, router, monkeypatch):
    """Si le site n'est ouvert nulle part, on ouvre normalement."""
    from core import browser_tabs

    monkeypatch.setattr(browser_tabs, "trouver_onglet", lambda *a, **k: None)
    monkeypatch.setattr(desktop, "trouver_fenetre", lambda *a, **k: None)
    ouvertes = []
    monkeypatch.setattr(websites, "open_url", lambda url: ouvertes.append(url) or True)
    reponse, _ = executer(router, assistant, "va sur Netflix")
    assert reponse.ok
    assert ouvertes and "netflix.com" in ouvertes[0]


def test_les_mentions_du_navigateur_sont_ignorees():
    """Chrome ajoute « Utilisation de la mémoire » au nom des onglets."""
    from core.browser_tabs import _nettoyer

    assert "youtube" in _nettoyer("(2) YouTube - Utilisation de la mémoire - 444 Mo")
    assert "memoire" not in _nettoyer("Netflix - Utilisation de la mémoire - 293 Mo")


@pytest.mark.parametrize("phrase", [
    "va sur l'onglet YouTube", "affiche l'onglet Netflix", "bascule sur Netflix",
    "reviens sur YouTube", "onglet Prime Video",
])
def test_formulations_centrees_sur_l_onglet(router, config, phrase):
    from core.context import Utterance

    utterance = Utterance.parse(phrase, wake_words=config.get("general.wake_words"))
    resolution = router.resolve(utterance, None)
    assert resolution is not None and resolution.command.name == "open_website", phrase
