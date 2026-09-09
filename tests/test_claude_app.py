"""
Parler à l'application Claude installée sur la machine.

Alma ne répond pas à la place de Claude : elle écrit la question dans la
fenêtre déjà ouverte et déjà connectée, attend, puis lit la réponse. Ces tests
n'ouvrent jamais la vraie application — ils la remplacent par un double, sans
quoi ils dépendraient de ce qui tourne sur la machine.
"""

import pytest

from core import claude_app
from core.context import Utterance
from commands import claude as commande_claude


class FausseFenetre:
    """Ce que `claude_app.fenetre()` rend : de quoi désigner une fenêtre."""

    handle = 4242
    titre = "Claude"
    processus = "claude.exe"
    ecran = 1


@pytest.fixture
def application(monkeypatch):
    """
    L'application Claude, ouverte et docile.

    Chaque étape est remplaçable : les tests qui veulent un échec précis
    réécrivent l'étape concernée.
    """
    fenetre = FausseFenetre()
    journal = {"questions": [], "clics": []}

    monkeypatch.setattr(claude_app, "fenetre", lambda: fenetre)
    monkeypatch.setattr(claude_app, "reveiller", lambda *a, **k: True)
    monkeypatch.setattr(claude_app, "conversation", lambda *a: "")
    monkeypatch.setattr(claude_app, "poser",
                        lambda _f, question: journal["questions"].append(question) or True)
    monkeypatch.setattr(claude_app, "attendre_la_reponse",
                        lambda *a, **k: "Un moteur de recherche est un annuaire du web.")
    monkeypatch.setattr(claude_app, "bouton",
                        lambda _f, libelle: journal["clics"].append(libelle) or "cible")
    monkeypatch.setattr("core.interaction.cliquer", lambda *a, **k: True)
    return journal


def router_vers(assistant, phrase):
    resolution = assistant.router.resolve(
        Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words")),
        assistant=assistant,
    )
    return resolution.command.name if resolution else "aucune"


# --------------------------------------------------------------------------
# Poser une question
# --------------------------------------------------------------------------
def test_la_question_part_dans_la_fenetre(assistant, application):
    reponse = assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert reponse.ok, reponse.text
    assert application["questions"] == ["ce qu'est un moteur de recherche"]


def test_la_reponse_est_lue_a_voix_haute(assistant, application):
    """C'est une question posée : la réponse doit être dite, pas seulement affichée."""
    reponse = assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert reponse.speak is True
    assert "annuaire du web" in reponse.text


def test_une_longue_reponse_est_ecourtee(assistant, application, monkeypatch):
    """On ne lit pas trois pages à voix haute : le reste est déjà à l'écran."""
    monkeypatch.setattr(claude_app, "attendre_la_reponse",
                        lambda *a, **k: "mot " * 400)
    reponse = assistant.handle("demande à Claude de raconter l'histoire du web")
    assert len(reponse.text) < commande_claude.LONGUEUR_PARLEE + 40
    assert "à l'écran" in reponse.text


def test_une_reponse_qui_ne_vient_pas_le_dit(assistant, application, monkeypatch):
    monkeypatch.setattr(claude_app, "attendre_la_reponse", lambda *a, **k: "")
    reponse = assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert not reponse.ok


def test_un_champ_introuvable_ne_fait_pas_semblant(assistant, application, monkeypatch):
    monkeypatch.setattr(claude_app, "poser", lambda *a: False)
    reponse = assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert not reponse.ok


def test_seule_la_nouveaute_est_rapportee(assistant, application, monkeypatch):
    """La conversation contient tout l'historique ; la réponse, c'est l'ajout."""
    monkeypatch.setattr(claude_app, "conversation", lambda *a: "échange précédent\n")
    vu = {}

    def attendre(_fenetre, avant, **_kw):
        vu["avant"] = avant
        return "neuf"

    monkeypatch.setattr(claude_app, "attendre_la_reponse", attendre)
    assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert vu["avant"] == "échange précédent\n"


# --------------------------------------------------------------------------
# Basculer entre Chat, Cowork et Code
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,libelle", [
    ("ouvre Cowork", "Chat and Cowork"),
    ("va sur Claude Cowork", "Chat and Cowork"),
    ("passe sur le chat", "Chat and Cowork"),
    ("ouvre Claude Code", "Code"),
    ("claude code", "Code"),
    ("montre les artifacts", "Artifacts"),
    ("nouvelle session Claude", "New"),
])
def test_les_sections_de_l_application(assistant, application, phrase, libelle):
    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " : " + reponse.text
    assert application["clics"] == [libelle]


def test_basculer_ne_se_commente_pas(assistant, application):
    """Une action se voit ; seule une question reçoit une réponse parlée."""
    assert assistant.handle("ouvre Cowork").speak is False


def test_un_bouton_introuvable_le_dit(assistant, application, monkeypatch):
    monkeypatch.setattr(claude_app, "bouton", lambda *a: None)
    assert not assistant.handle("ouvre Cowork").ok


def test_un_clic_sans_effet_ne_se_declare_pas_reussi(assistant, application, monkeypatch):
    monkeypatch.setattr("core.interaction.cliquer", lambda *a, **k: False)
    assert not assistant.handle("ouvre Cowork").ok


# --------------------------------------------------------------------------
# Application fermée : on retombe sur le navigateur
# --------------------------------------------------------------------------
def test_sans_application_la_question_part_au_navigateur(assistant):
    """`application_claude_fermee` s'applique : la fenêtre n'existe pas."""
    assert router_vers(assistant, "demande à Claude ce qu'est un moteur de recherche") \
        == "ask_claude"


def test_avec_application_la_question_reste_sur_la_machine(assistant, application):
    assert router_vers(assistant, "demande à Claude ce qu'est un moteur de recherche") \
        == "claude_demander"


def test_sans_application_les_sections_ne_captent_rien(assistant):
    """« ouvre Cowork » ne doit pas mobiliser une commande inutilisable."""
    assert router_vers(assistant, "ouvre Claude Code") != "claude_section"


# --------------------------------------------------------------------------
# Ce que le module de pilotage garantit tout seul
# --------------------------------------------------------------------------
def test_la_nouveaute_est_ce_qui_a_ete_ajoute():
    assert claude_app._nouveaute("bonjour", "bonjour et voici la suite") \
        == "et voici la suite"


def test_la_nouveaute_tolere_un_texte_qui_a_ete_reecrit():
    """Si l'affichage a été recomposé, on rend ce qu'on lit plutôt que rien."""
    assert claude_app._nouveaute("bonjour", "tout autre chose") == "tout autre chose"


def test_les_blancs_de_l_interface_ne_sont_pas_lus():
    assert claude_app._nouveaute("", "  une   réponse \n\n aérée ") == "une réponse aérée"


def test_aucune_cle_d_api_n_est_utilisee():
    """
    Le travail est fait par l'application déjà connectée, avec l'abonnement de
    l'utilisateur. Ce module ne doit contacter personne.
    """
    from pathlib import Path

    source = Path(claude_app.__file__).read_text(encoding="utf-8")
    for interdit in ("requests", "urllib", "api_key", "ANTHROPIC_API_KEY", "http"):
        assert interdit not in source, interdit + " n'a rien à faire ici"
