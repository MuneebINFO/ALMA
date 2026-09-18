"""
Le relais : ce qu'il laisse passer, ce qu'il compte, ce qu'il ne garde pas.

Aucun test ici n'appelle Anthropic ni Microsoft. Ce qui est vérifié, ce sont
les décisions du relais — qui passe, qui est compté, qui est refusé — pas la
capacité d'un tiers à répondre.

Le test le plus important du fichier est le dernier : la base ne doit contenir
aucune trace du contenu des requêtes. PRIVACY.md le promet aux utilisateurs,
et une promesse de confidentialité qu'aucun test ne garde est une promesse
qui se perdra à la première refonte.

Lancer : pytest relais/test_relais.py
"""

import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")


@pytest.fixture
def relais(tmp_path, monkeypatch):
    """Un relais neuf, base temporaire, en mode developpement."""
    monkeypatch.setenv("ALMA_BASE", str(tmp_path / "relais.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fausse-cle")
    monkeypatch.setenv("ALMA_JETON_ESSAI", "jeton-de-test")
    monkeypatch.setenv("ALMA_QUOTA_MENSUEL", "3")
    monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
    monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)

    import relais as module
    importlib.reload(module)
    return module


@pytest.fixture
def client(relais, monkeypatch):
    """Le service, avec l'amont remplacé par une doublure."""
    from fastapi.testclient import TestClient

    envoyees = []

    class ReponseFactice:
        status_code = 200

        @staticmethod
        def json():
            return {"content": [{"type": "text", "text": "réponse"}]}

    class ClientFactice:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None, **k):
            envoyees.append((url, content, headers))
            return ReponseFactice()

    monkeypatch.setattr(relais.httpx, "AsyncClient", ClientFactice)
    essai = TestClient(relais.app)
    essai.envoyees = envoyees
    return essai


def poster(client, jeton, corps=None):
    return client.post("/v1/messages",
                       headers={"x-api-key": jeton},
                       json=corps or {"model": "claude-sonnet-5",
                                      "messages": [{"role": "user",
                                                    "content": "bonjour"}]})


# --------------------------------------------------------------------------
# Qui passe, qui ne passe pas
# --------------------------------------------------------------------------
def test_sans_jeton_rien_ne_passe(client):
    assert poster(client, "").status_code == 401


def test_un_jeton_inconnu_est_refuse(client):
    assert poster(client, "jeton-invente").status_code == 401


def test_le_mode_developpement_n_ouvre_pas_a_tout_le_monde(client):
    """
    La panne qui coûterait cher en silence : un relais mal configuré qui
    laisserait passer n'importe qui, et facturerait le propriétaire de la clé.
    """
    for jeton in ("", "n'importe quoi", "admin", "sk-ant-quelque-chose"):
        assert poster(client, jeton).status_code == 401, jeton

    assert poster(client, "jeton-de-test").status_code == 200


def test_un_abonne_valide_passe(client):
    assert poster(client, "jeton-de-test").status_code == 200


# --------------------------------------------------------------------------
# La clé
# --------------------------------------------------------------------------
def test_la_cle_du_relais_remplace_celle_du_client(client):
    """
    Le cœur du dispositif : le client envoie un jeton d'abonné, et c'est la
    clé du relais qui part vers Anthropic. Le jeton ne doit jamais fuiter
    vers l'amont, où il n'aurait aucun sens.
    """
    poster(client, "jeton-de-test")

    _url, _corps, entetes = client.envoyees[0]
    assert entetes["x-api-key"] == "sk-ant-fausse-cle"
    assert "jeton-de-test" not in str(entetes)


def test_les_entetes_non_declarees_sont_jetees(client):
    """
    Un relais qui transmet aveuglément devient le proxy ouvert de quelqu'un
    d'autre.
    """
    client.post("/v1/messages",
                headers={"x-api-key": "jeton-de-test",
                         "x-injecte": "valeur",
                         "authorization": "Bearer autre-chose"},
                json={"messages": []})

    _url, _corps, entetes = client.envoyees[0]
    assert "x-injecte" not in entetes
    assert "authorization" not in entetes


# --------------------------------------------------------------------------
# Le quota
# --------------------------------------------------------------------------
def test_le_quota_finit_par_bloquer(client):
    """Quota de 3 dans ce test : la quatrième requête doit être refusée."""
    for _ in range(3):
        assert poster(client, "jeton-de-test").status_code == 200

    refusee = poster(client, "jeton-de-test")
    assert refusee.status_code == 429
    assert "uota" in refusee.json()["detail"]


def test_le_quota_est_par_abonne(client, relais):
    """Un gros utilisateur ne doit pas épuiser le quota des autres."""
    relais.compter_une_requete("premier")
    relais.compter_une_requete("premier")

    assert relais.consommation("premier") == 2
    assert relais.consommation("second") == 0


def test_une_panne_de_l_amont_ne_consomme_pas_le_quota(client, relais, monkeypatch):
    """
    Facturer un quota pour une panne de notre côté, c'est faire payer
    l'utilisateur pour notre incident.
    """
    class Echec:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            raise relais.httpx.ConnectError("amont injoignable")

    monkeypatch.setattr(relais.httpx, "AsyncClient", Echec)

    assert poster(client, "jeton-de-test").status_code == 502
    assert relais.consommation("jeton-de-test") == 0


# --------------------------------------------------------------------------
# Ce qui n'est PAS conservé
# --------------------------------------------------------------------------
def test_la_base_ne_garde_aucun_contenu(client, relais):
    """
    LE test de ce fichier. PRIVACY.md promet que le relais ne conserve ni les
    questions, ni les images, ni les réponses — seulement un compteur. Si
    cette promesse se perd un jour dans une refonte, c'est ici qu'on doit
    l'apprendre, et pas dans la presse.
    """
    secret = "mon-numero-de-carte-est-4242424242424242"
    poster(client, "jeton-de-test",
           {"model": "claude-sonnet-5",
            "messages": [{"role": "user", "content": secret}]})

    with open(os.environ["ALMA_BASE"], "rb") as fichier:
        octets = fichier.read()

    assert secret.encode() not in octets
    assert b"4242424242424242" not in octets
    assert b"bonjour" not in octets
    # Le compteur, lui, doit bien etre la : sinon le test ci-dessus passerait
    # pour une base vide, sans rien prouver.
    assert relais.consommation("jeton-de-test") == 1


def test_le_schema_n_a_aucune_colonne_ou_ranger_un_contenu(relais):
    """
    La garantie structurelle : il n'y a pas de colonne pour une question,
    donc il ne peut pas y avoir de question rangée.
    """
    import sqlite3

    with sqlite3.connect(os.environ["ALMA_BASE"]) as lien:
        lien.executescript(relais.SCHEMA)
        tables = [t[0] for t in lien.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        colonnes = set()
        for table in tables:
            for ligne in lien.execute("PRAGMA table_info(" + table + ")"):
                colonnes.add(ligne[1])

    assert colonnes == {"abonne", "periode", "compte", "valide", "verifie"}, colonnes


# --------------------------------------------------------------------------
# Le service lui-même
# --------------------------------------------------------------------------
def test_la_sante_repond_et_dit_son_mode(client):
    reponse = client.get("/sante")

    assert reponse.status_code == 200
    assert reponse.json()["mode"] == "developpement"
    assert reponse.json()["quota_mensuel"] == 3
