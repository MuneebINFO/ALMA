"""
Le coffre : ce qui chiffre la clé d'API de l'utilisateur.

C'est le module le plus sensible du projet, et le seul dont le fixture
`aucune_trace_sur_la_machine` neutralise les trois fonctions — précisément
pour qu'aucun autre test n'aille lire le vrai coffre de qui lance la suite.

Ici on remet les VRAIES fonctions, mais dirigées vers un fichier temporaire.
C'est le seul fichier du projet qui a le droit de chiffrer pour de bon.
"""

import json

import pytest

from core import secrets

# Capturées à l'import, avant que le fixture autouse ne pose ses doublures.
VRAI_POSER = secrets.poser
VRAI_LIRE = secrets.lire
VRAI_OUBLIER = secrets.oublier
VRAI_PRESENT = secrets.present


@pytest.fixture
def coffre(tmp_path, monkeypatch):
    """Le vrai coffre, dans un dossier temporaire."""
    monkeypatch.setattr(secrets, "poser", VRAI_POSER)
    monkeypatch.setattr(secrets, "lire", VRAI_LIRE)
    monkeypatch.setattr(secrets, "oublier", VRAI_OUBLIER)
    fichier = tmp_path / "secrets.json"
    monkeypatch.setattr(secrets, "_fichier", lambda config=None: fichier)
    return fichier


# --------------------------------------------------------------------------
# L'aller-retour
# --------------------------------------------------------------------------
def test_ce_qu_on_pose_se_relit(coffre):
    assert secrets.poser("cle", "sk-ant-valeur-secrete") is True
    assert secrets.lire("cle") == "sk-ant-valeur-secrete"


def test_un_coffre_vide_ne_rend_rien(coffre):
    assert secrets.lire("cle") == ""
    assert VRAI_PRESENT("cle") is False


def test_plusieurs_valeurs_cohabitent(coffre):
    secrets.poser("une", "première")
    secrets.poser("autre", "seconde")

    assert secrets.lire("une") == "première"
    assert secrets.lire("autre") == "seconde"


def test_reposer_remplace(coffre):
    secrets.poser("cle", "ancienne")
    secrets.poser("cle", "nouvelle")

    assert secrets.lire("cle") == "nouvelle"


# --------------------------------------------------------------------------
# Ce qui compte vraiment : que ça ne se lise pas
# --------------------------------------------------------------------------
def test_la_valeur_n_apparait_nulle_part_en_clair(coffre):
    """
    La raison d'être du module. Si la clé se retrouvait lisible dans le
    fichier, tout le chiffrement n'aurait servi qu'à se donner bonne
    conscience.
    """
    secrets.poser("cle", "sk-ant-api03-valeur-tres-reconnaissable")

    octets = coffre.read_bytes()
    assert b"sk-ant-api03-valeur-tres-reconnaissable" not in octets
    assert b"valeur-tres-reconnaissable" not in octets
    # Et pas davantage dans la structure lisible du fichier.
    assert "reconnaissable" not in json.dumps(json.loads(coffre.read_text()))


def test_aucune_valeur_ne_part_dans_le_journal(coffre, caplog):
    """
    Un extrait de clé dans un fichier de log est une clé fuitée. Le module
    journalise des échecs, jamais des valeurs — même tronquées.
    """
    import logging

    with caplog.at_level(logging.DEBUG):
        secrets.poser("cle", "sk-ant-ne-doit-pas-etre-journalisee")
        secrets.lire("cle")
        secrets.oublier("cle")

    trace = caplog.text
    for fragment in ("sk-ant", "ne-doit-pas", "journalisee"):
        assert fragment not in trace, trace


# --------------------------------------------------------------------------
# Ce qui ne doit jamais lever
# --------------------------------------------------------------------------
def test_un_fichier_abime_se_comporte_comme_un_coffre_vide(coffre):
    """
    Alma doit retomber en édition libre — qui marche sans rien — plutôt que
    de refuser de démarrer parce qu'un fichier est corrompu.
    """
    coffre.write_text("ceci n'est pas du JSON {{{", encoding="utf-8")

    assert secrets.lire("cle") == ""


def test_un_blob_indechiffrable_se_comporte_comme_un_coffre_vide(coffre):
    """
    Le cas réel : le coffre a été posé sous un AUTRE compte Windows. DPAPI
    refuse alors de déchiffrer, et c'est le comportement voulu — mais cela ne
    doit pas remonter en exception.
    """
    coffre.write_text(json.dumps({"cle": "bm90LXVuLWJsb2ItZHBhcGk="}),
                      encoding="utf-8")

    assert secrets.lire("cle") == ""


def test_poser_une_valeur_vide_efface(coffre):
    secrets.poser("cle", "quelque chose")
    assert secrets.poser("cle", "") is True

    assert secrets.lire("cle") == ""


def test_oublier_une_valeur_absente_ne_se_plaint_pas(coffre):
    assert secrets.oublier("jamais-posee") is True


def test_le_dernier_oubli_retire_le_fichier(coffre):
    """
    Un « {} » laissé derrière laisserait croire qu'il reste quelque chose.
    """
    secrets.poser("cle", "valeur")
    assert coffre.exists()

    secrets.oublier("cle")

    assert not coffre.exists()
