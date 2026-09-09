"""
Le modèle de langage local, en dernier recours.

Il ne remplace pas le moteur de règles : il prend la parole quand aucune règle
ne correspond, là où Alma répondait « Je n'ai pas compris » et s'arrêtait. Il
RÉPOND — il n'exécute rien.

Comme tout ce point d'extension, il est désactivé par défaut : aucun appel ne
part tant que `ai_fallback.enabled` vaut false.
"""

import json

import pytest

from core import ai_fallback
from core.providers.ollama_provider import OllamaProvider, _raccourcir


class ReponseFactice:
    def __init__(self, charge, code=200):
        self._charge = charge
        self.code = code

    def raise_for_status(self):
        if self.code >= 400:
            raise RuntimeError("HTTP " + str(self.code))

    def json(self):
        if isinstance(self._charge, Exception):
            raise self._charge
        return self._charge


@pytest.fixture
def serveur(monkeypatch, config):
    """Un Ollama simulé : on observe ce qui lui est envoyé."""
    import requests

    etat = {"envois": [], "modeles": ["qwen2.5:3b"], "reponse": "Bonjour."}

    def get(url, **k):
        if not etat["modeles"]:
            raise ConnectionError("injoignable")
        return ReponseFactice({"models": [{"name": m} for m in etat["modeles"]]})

    def post(url, json=None, **k):
        etat["envois"].append(json)
        if isinstance(etat["reponse"], Exception):
            raise etat["reponse"]
        return ReponseFactice({"response": etat["reponse"]})

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(requests, "post", post)
    return etat


# --------------------------------------------------------------------------
# Rien ne part tant que ce n est pas active
# --------------------------------------------------------------------------
def test_desactive_par_defaut(config):
    assert config.get("ai_fallback.enabled") is False
    assert ai_fallback.get_provider(config).name == "none"


def test_aucun_appel_quand_desactive(config, serveur):
    """Le garde-fou du projet : pas d'appel réseau tant que enabled est faux."""
    ai_fallback.handle_with_ai("explique-moi la photosynthèse", config)
    assert serveur["envois"] == []


@pytest.fixture
def actif(config, monkeypatch):
    monkeypatch.setitem(config.data["ai_fallback"], "enabled", True)
    monkeypatch.setitem(config.data["ai_fallback"], "provider", "ollama")
    return config


def test_active_le_provider_est_ollama(actif):
    assert ai_fallback.get_provider(actif).name == "ollama"


# --------------------------------------------------------------------------
# Ce qui est envoye
# --------------------------------------------------------------------------
def test_la_question_est_transmise_telle_quelle(actif, serveur):
    serveur["reponse"] = "La photosynthèse convertit la lumière en sucre."
    reponse = ai_fallback.handle_with_ai("explique-moi la photosynthèse", actif)
    assert reponse == "La photosynthèse convertit la lumière en sucre."
    assert serveur["envois"][0]["prompt"] == "explique-moi la photosynthèse"


def test_le_modele_est_prevenu_quil_ne_peut_rien_faire(actif, serveur):
    """
    Sans cela, il propose d'ouvrir des applications et d'appuyer sur des
    touches — des promesses qu'il ne peut pas tenir et qu'Alma ne relaiera pas.
    """
    ai_fallback.handle_with_ai("ouvre Photoshop", actif)
    consigne = serveur["envois"][0]["system"].lower()
    assert "rien" in consigne and "ordinateur" in consigne
    assert "français" in consigne


def test_rien_ne_part_vers_lexterieur(actif, serveur):
    """L'hôte reste la machine : c'est tout l'intérêt d'un modèle local."""
    provider = OllamaProvider(actif)
    assert provider.hote.startswith("http://localhost") or "127.0.0.1" in provider.hote


# --------------------------------------------------------------------------
# Quand ca ne marche pas, on le dit
# --------------------------------------------------------------------------
def test_serveur_absent(actif, serveur):
    serveur["modeles"] = []
    reponse = ai_fallback.handle_with_ai("bonjour", actif)
    assert "ollama.com" in reponse.lower()
    assert serveur["envois"] == [], "rien ne devait être envoyé"


def test_modele_non_telecharge(actif, serveur):
    serveur["modeles"] = ["llama3:8b"]
    reponse = ai_fallback.handle_with_ai("bonjour", actif)
    assert "ollama pull" in reponse
    assert serveur["envois"] == []


def test_le_nom_du_modele_tolere_un_suffixe(actif, serveur):
    """« qwen2.5:3b » et « qwen2.5:3b-instruct » sont la même famille."""
    serveur["modeles"] = ["qwen2.5:3b-instruct-q4_K_M"]
    serveur["reponse"] = "Voilà."
    assert ai_fallback.handle_with_ai("bonjour", actif) == "Voilà."


def test_delai_depasse(actif, serveur):
    import requests

    serveur["reponse"] = requests.Timeout()
    reponse = ai_fallback.handle_with_ai("bonjour", actif)
    assert "secondes" in reponse and "petit" in reponse


def test_une_panne_ne_remonte_pas_en_exception(actif, serveur):
    serveur["reponse"] = RuntimeError("boum")
    reponse = ai_fallback.handle_with_ai("bonjour", actif)
    assert reponse and "RuntimeError" in reponse


def test_reponse_vide(actif, serveur):
    serveur["reponse"] = "   "
    assert "rien répondu" in ai_fallback.handle_with_ai("bonjour", actif)


# --------------------------------------------------------------------------
# Une reponse parlee doit rester courte
# --------------------------------------------------------------------------
def test_une_reponse_trop_longue_est_coupee_a_une_phrase():
    long = ("Première phrase courte. " + "Un développement interminable " * 30
            + "Fin.")
    coupe = _raccourcir(long)
    assert len(coupe) <= 400
    assert coupe.endswith(".") or coupe.endswith("…")


def test_une_reponse_courte_nest_pas_touchee():
    assert _raccourcir("  Il est midi.  ") == "Il est midi."


def test_les_espaces_sont_normalises():
    assert _raccourcir("deux\n\nlignes   collees") == "deux lignes collees"
