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
def application(monkeypatch, assistant):
    """
    L'application Claude, ouverte et docile, et l'utilisateur qui dit oui.

    Chaque étape est remplaçable : les tests qui veulent un échec précis, ou
    un refus, réécrivent l'étape concernée.
    """
    assistant.io.answers = ["oui"] * 10
    fenetre = FausseFenetre()
    journal = {"questions": [], "clics": []}

    monkeypatch.setattr(claude_app, "fenetre", lambda: fenetre)
    monkeypatch.setattr(claude_app, "reveiller", lambda *a, **k: True)
    monkeypatch.setattr(claude_app, "conversation", lambda *a: "")
    monkeypatch.setattr(claude_app, "etat", lambda *a: (0, ""))
    monkeypatch.setattr(claude_app, "poser",
                        lambda _f, question: journal["questions"].append(question) or True)
    monkeypatch.setattr(claude_app, "attendre_la_reponse",
                        lambda *a, **k: "Un moteur de recherche est un annuaire du web.")
    monkeypatch.setattr(claude_app, "bouton",
                        lambda _f, libelle: journal["clics"].append(libelle) or "cible")
    monkeypatch.setattr(claude_app, "activer",
                        lambda _f, libelle, **k: journal["clics"].append(libelle) or True)
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


def test_l_etat_d_avant_est_transmis_a_l_attente(assistant, application, monkeypatch):
    """
    Ce qu'on relève avant l'envoi doit être COMPARABLE à ce qu'on lira après.

    Le piège mesuré : sur une page vierge il n'y a aucun message, et le texte
    entier vaut alors trois mille caractères de barre latérale, que l'échange
    de quarante caractères ne dépassera jamais. Un nombre de messages et un
    texte, relevés ensemble, évitent de comparer l'un à l'autre.
    """
    monkeypatch.setattr(claude_app, "etat", lambda *a: (2, "échange précédent"))
    vu = {}

    def attendre(_fenetre, avant, **_kw):
        vu["avant"] = avant
        return "neuf"

    monkeypatch.setattr(claude_app, "attendre_la_reponse", attendre)
    assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert vu["avant"] == (2, "échange précédent")


def test_la_question_ouvre_une_conversation_neuve(assistant, application):
    """
    Sinon elle atterrit dans ce qui est affiché — une session Claude Code au
    travail, par exemple — et s'y mélange à autre chose. Le chat d'abord :
    « New » depuis la section Code créerait une session de code.
    """
    assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert application["clics"] == ["Chat and Cowork", "New"]


def test_la_permission_est_demandee_avant_d_ouvrir(assistant, application):
    assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    demandes = [texte for texte in assistant.io.written if "?" in texte]
    assert any("nouvelle conversation" in texte.lower() for texte in demandes), demandes


def test_un_refus_n_ecrit_rien(assistant, application):
    assistant.io.answers = ["non"]
    reponse = assistant.handle("demande à Claude ce qu'est un moteur de recherche")
    assert application["questions"] == []
    assert application["clics"] == []
    assert reponse.speak is False


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
# Lancer une tâche dans Cowork
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase,tache", [
    ("demande à Cowork de trier mes captures d'écran", "trier mes captures d'écran"),
    ("lance une tâche Cowork : résumer mes notes", "résumer mes notes"),
    ("résumer mes notes en Cowork", "résumer mes notes"),
])
def test_une_tache_cowork_part_en_une_commande(assistant, application, phrase, tache):
    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " : " + reponse.text
    assert application["questions"] == [tache]


def test_une_tache_cowork_ouvre_une_session_neuve_et_le_bon_mode(assistant, application):
    """
    L'ordre compte : le sélecteur Chat/Cowork n'existe que sur une page vierge,
    et sans page vierge la tâche partirait dans la conversation affichée.
    """
    assistant.handle("demande à Cowork de trier mes captures d'écran")
    assert application["clics"] == ["New", "Cowork"]


def test_sans_mode_cowork_rien_n_est_envoye(assistant, application, monkeypatch):
    """Mieux vaut ne rien faire que d'envoyer la tâche dans un simple chat."""
    monkeypatch.setattr(claude_app, "activer",
                        lambda _f, libelle, **k: libelle != "Cowork")
    reponse = assistant.handle("demande à Cowork de trier mes captures d'écran")
    assert not reponse.ok
    assert application["questions"] == []


def test_une_tache_cowork_ne_se_commente_pas(assistant, application):
    assert assistant.handle("demande à Cowork de trier mes notes").speak is False


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


class FauxElement:
    """Un élément d'accessibilité réduit à ce que le module lui demande."""

    def __init__(self, rect, nom="", type_controle=50020):
        self.CurrentBoundingRectangle = type("R", (), dict(
            zip(("left", "top", "right", "bottom"), rect)))()
        self.CurrentName = nom
        self.CurrentControlType = type_controle


def arbre(monkeypatch, elements):
    monkeypatch.setattr(claude_app, "_parcourir",
                        lambda _cible: ([(e, e.CurrentControlType, e.CurrentName)
                                         for e in elements], object()))


# Ce que la fenêtre expose vraiment, mesuré sur l'application : les messages
# sont nommés, l'horodatage vit dans « Message actions », et les annonces pour
# lecteur d'écran mesurent deux pixels sur trois.
ECHANGE = [
    FauxElement((591, 164, 1600, 274), "Message 1 of 2", 50026),
    FauxElement((1115, 181, 1578, 207), "pourquoi le ciel est bleu"),
    FauxElement((1405, 235, 1600, 269), "Message actions", 50021),
    FauxElement((1405, 242, 1494, 262), "1 minute ago"),
    FauxElement((591, 279, 1600, 422), "Message 2 of 2", 50026),
    FauxElement((590, 277, 592, 280), "Claude responded: à cause de la diffusion…"),
    FauxElement((597, 281, 1548, 375), "À cause de la diffusion de Rayleigh."),
    FauxElement((589, 388, 1600, 422), "Message actions", 50021),
    FauxElement((761, 395, 849, 415), "1 minute ago"),
    # La barre latérale : plus longue que l'échange, et sans rapport avec lui.
    FauxElement((52, 623, 260, 645), "Coût de la certification"),
]


def test_les_messages_sont_lus_dans_l_ordre(monkeypatch):
    arbre(monkeypatch, ECHANGE)
    assert claude_app.messages(None) == [
        "pourquoi le ciel est bleu",
        "À cause de la diffusion de Rayleigh.",
    ]


def test_l_horodatage_n_est_pas_lu(monkeypatch):
    """« il y a une minute » collé à la réponse n'apprend rien."""
    arbre(monkeypatch, ECHANGE)
    assert not any("minute" in message for message in claude_app.messages(None))


def test_les_annonces_pour_lecteur_d_ecran_sont_ignorees(monkeypatch):
    """Elles répètent la réponse en la tronquant, sur deux pixels de haut."""
    arbre(monkeypatch, ECHANGE)
    assert not any("Claude responded" in m for m in claude_app.messages(None))


def test_la_barre_laterale_n_est_pas_la_conversation(monkeypatch):
    """
    Le vrai piège : elle contient la liste des conversations, donc plus de
    texte que l'échange lui-même.
    """
    arbre(monkeypatch, ECHANGE)
    assert "certification" not in claude_app.conversation(None)


def test_l_etat_compte_les_messages_et_garde_le_texte(monkeypatch):
    arbre(monkeypatch, ECHANGE)
    nombre, texte = claude_app.etat(None)
    assert nombre == 2
    assert "Rayleigh" in texte


def test_l_attente_ne_confond_pas_les_deux_mesures(monkeypatch):
    """
    Sans découpage, on compare des textes ; avec, des messages. Mélanger les
    deux faisait attendre le délai complet — 95 secondes pour « Lisbonne ».
    """
    arbre(monkeypatch, ECHANGE)
    monkeypatch.setattr(claude_app, "STABILITE_REQUISE", 0)
    monkeypatch.setattr(claude_app, "PAUSE_SONDAGE", 0)
    # Page vierge avant l'envoi : aucun message, et un texte long sans rapport.
    depart = (0, "x" * 3000)
    assert claude_app.attendre_la_reponse(None, depart, delai=2)         == "À cause de la diffusion de Rayleigh."


def test_l_attente_ne_relit_pas_la_question(monkeypatch):
    """Envoyer ajoute deux messages : le nôtre, puis la réponse."""
    arbre(monkeypatch, ECHANGE)
    monkeypatch.setattr(claude_app, "STABILITE_REQUISE", 0)
    monkeypatch.setattr(claude_app, "PAUSE_SONDAGE", 0)
    # Un seul message de plus qu'au départ : c'est la question, pas la réponse.
    assert claude_app.attendre_la_reponse(None, (1, ""), delai=0.5) == ""


def test_la_reponse_est_le_dernier_message(monkeypatch):
    arbre(monkeypatch, ECHANGE)
    assert claude_app._reponse(None, "", "") == "À cause de la diffusion de Rayleigh."


def test_les_icones_ne_sont_pas_lues():
    """U+FFFC remplace images et icônes dans le texte de l'accessibilité."""
    assert claude_app._propre("Voici ￼ la suite") == "Voici la suite"


def test_aucune_cle_d_api_n_est_utilisee():
    """
    Le travail est fait par l'application déjà connectée, avec l'abonnement de
    l'utilisateur. Ce module ne doit contacter personne.
    """
    from pathlib import Path

    source = Path(claude_app.__file__).read_text(encoding="utf-8")
    for interdit in ("requests", "urllib", "api_key", "ANTHROPIC_API_KEY", "http"):
        assert interdit not in source, interdit + " n'a rien à faire ici"
