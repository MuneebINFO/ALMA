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
    """Aucun site n'est ouvert : tout doit passer par une ouverture classique."""
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
    fenetre = desktop.Fenetre(handle=7, titre="Netflix - Google Chrome",
                              processus="chrome.exe", ecran=1)
    monkeypatch.setattr(desktop, "trouver_fenetre", lambda *a, **k: fenetre)
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
