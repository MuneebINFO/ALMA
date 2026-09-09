"""
Poser la question au mode IA de Google, par le navigateur, en arrière-plan.

Aucune API, aucune clé. ALMA ouvre la recherche dans une fenêtre qu'elle
réduit aussitôt, la lit comme n'importe quelle page, puis la referme.

Aucun de ces tests n'ouvre de navigateur : la page est remplacée par le texte
qu'elle exposerait. Ils verrouillent l'extraction — c'est là qu'était la
difficulté — et le partage entre une question et une action.
"""

import pytest

from core import deduction
from core.providers import gemini_provider
from core.providers.gemini_provider import GeminiProvider


@pytest.fixture
def lecture(monkeypatch):
    """Remplace la lecture de la page par un texte donné."""
    def poser(*lignes):
        monkeypatch.setattr(gemini_provider, "_texte_de_la_page",
                            lambda _f: "\n".join(lignes) + "\n")
    return poser


QUESTION = "pourquoi le ciel est bleu"
ATTENDU = ("Le ciel est bleu parce que la lumière du Soleil interagit avec "
           "l'atmosphère terrestre, un phénomène appelé diffusion de Rayleigh.")

# Ce que la page expose vraiment, mesuré sur le mode IA : l'en-tête, la
# question rappelée, la réponse, puis les sources, des puces et — plus bas —
# des résultats dont le titre reprend mot pour mot la question.
PAGE_REELLE = (
    "Passer directement au contenu principal",
    "Mode IA",
    "Tous",
    "Images",
    "Compte Google Machin (machin@example.com), Abonnement Google",
    "￼",
    QUESTION,
    "￼",
    ATTENDU,
    "Météo-France (+ 1) - Pourquoi le ciel est-il bleu ? | Météo-France. Résultats associés",
    "Voici comment cela fonctionne en trois étapes simples :",
    "• Une lumière de toutes les couleurs : la lumière du Soleil semble blanche.",
    "Pourquoi le ciel est bleu",
    "Pourquoi le ciel est bleu ? questions. dis Noura pourquoi elle est bleue…",
)


# --------------------------------------------------------------------------
# Lire la réponse dans la page
# --------------------------------------------------------------------------
def test_la_reponse_suit_la_question_rappelee(lecture):
    lecture(*PAGE_REELLE)
    assert gemini_provider.reponse(None, QUESTION) == ATTENDU


def test_la_question_reprise_plus_bas_ne_trompe_pas(lecture):
    """
    Le défaut mesuré : « pourquoi le ciel est bleu » est aussi le titre d'une
    vidéo, plus bas dans la page. En partant de la dernière occurrence, ALMA
    lisait le descriptif de la vidéo à la place de la réponse.
    """
    lecture(*PAGE_REELLE)
    assert "Noura" not in gemini_provider.reponse(None, QUESTION)


def test_ce_qui_precede_la_question_est_ignore(lecture):
    """Sans cela, le nom du compte Google passerait pour une réponse."""
    lecture(*PAGE_REELLE)
    assert "Compte Google" not in gemini_provider.reponse(None, QUESTION)


def test_les_sources_et_les_puces_ne_sont_pas_lues(lecture):
    """Écrites, elles se parcourent ; dites, elles se subissent."""
    lecture(*PAGE_REELLE)
    trouvee = gemini_provider.reponse(None, QUESTION)
    assert "Météo-France" not in trouvee and "trois étapes" not in trouvee


def test_les_images_ne_sont_pas_lues(lecture):
    """U+FFFC remplace les images dans le texte de l'accessibilité."""
    lecture("combien vit une abeille", "￼",
            "Une abeille ouvrière vit de quatre à six semaines en été.")
    assert gemini_provider.reponse(None, "combien vit une abeille") == (
        "Une abeille ouvrière vit de quatre à six semaines en été."
    )


def test_une_reponse_courte_est_gardee_si_elle_se_termine(lecture):
    """« Victor Hugo. » est court, mais c'est une phrase."""
    lecture("qui a écrit Les Misérables", "￼", "Victor Hugo.")
    assert gemini_provider.reponse(None, "qui a écrit Les Misérables") == "Victor Hugo."


def test_la_casse_et_les_blancs_ne_font_pas_manquer_la_question(lecture):
    """La page peut rappeler la question autrement qu'on ne l'a dictée."""
    lecture("Quelle est   la Capitale du Portugal", "La capitale du Portugal est Lisbonne.")
    assert gemini_provider.reponse(None, "quelle est la capitale du portugal") == (
        "La capitale du Portugal est Lisbonne."
    )


def test_sans_reponse_on_ne_rend_rien(lecture):
    """Tant que la page n'a rien écrit, mieux vaut rien qu'un bout d'interface."""
    lecture("Mode IA", "Tous", "Images", "Chargement…")
    assert gemini_provider.reponse(None, QUESTION) == ""


def test_une_page_vide_ne_fait_pas_tomber(lecture):
    lecture("")
    assert gemini_provider.reponse(None, QUESTION) == ""


# --------------------------------------------------------------------------
# Ce que le provider promet autour
# --------------------------------------------------------------------------
def test_aucune_cle_n_est_demandee():
    """C'est tout l'intérêt : la page suffit."""
    from pathlib import Path

    source = Path(gemini_provider.__file__).read_text(encoding="utf-8")
    for interdit in ("API_KEY", "api_key", "googleapis.com"):
        assert interdit not in source


def test_c_est_le_mode_ia_qui_est_interroge():
    """
    Et non gemini.google.com : mesuré, celui-là ne répond que fenêtre au
    premier plan — réduite ou masquée, la réponse n'arrive jamais.
    """
    assert "udm=50" in gemini_provider.RECHERCHE
    assert "gemini.google.com" not in gemini_provider.RECHERCHE


def test_sans_navigateur_il_le_dit(config, monkeypatch):
    monkeypatch.setattr(GeminiProvider, "navigateur", lambda self: "")
    assert "Chrome" in GeminiProvider(config).generate("pourquoi le ciel est bleu")


def test_une_question_vide_n_ouvre_rien(config, monkeypatch):
    ouvertures = []
    monkeypatch.setattr(gemini_provider, "_ouvrir_discretement",
                        lambda *a: ouvertures.append(a))
    GeminiProvider(config).generate("   ")
    assert ouvertures == []


def test_la_fenetre_est_refermee_meme_en_cas_d_echec(config, monkeypatch):
    """Sinon les fenêtres s'accumulent, une par question posée."""
    fermees = []
    monkeypatch.setattr(GeminiProvider, "navigateur", lambda self: "chrome.exe")
    monkeypatch.setattr(gemini_provider, "_ouvrir_discretement", lambda *a: "la-fenetre")
    monkeypatch.setattr(gemini_provider, "_fermer", lambda f: fermees.append(f))

    def echoue(*a, **k):
        raise RuntimeError("page illisible")

    monkeypatch.setattr(gemini_provider, "_attendre_la_reponse", echoue)
    trouvee = GeminiProvider(config).generate("pourquoi le ciel est bleu")
    assert fermees == ["la-fenetre"]
    assert "pas trouvé" in trouvee


def test_une_reponse_trop_longue_est_coupee_a_une_fin_de_phrase():
    coupe = gemini_provider._raccourcir(("Une phrase complète. " * 60).strip())
    assert len(coupe) <= gemini_provider.LONGUEUR_MAX
    assert coupe.endswith(".")


# --------------------------------------------------------------------------
# Ce qui part, et ce qui ne part pas
# --------------------------------------------------------------------------
@pytest.mark.parametrize("phrase", [
    "quelle est la capitale du Portugal",
    "pourquoi le ciel est bleu",
    "c'est quoi la photosynthèse",
    "explique-moi la relativité",
    "combien de planètes dans le système solaire",
    "qui a écrit Les Misérables",
    "est-ce que les pandas hibernent",
    "ça veut dire quoi éphémère",
    "raconte-moi une histoire",
    "dis-moi la population de la Belgique",
])
def test_une_question_est_reconnue(phrase):
    assert deduction.est_une_question(phrase)


@pytest.mark.parametrize("phrase", [
    "ouvre Chrome",
    "mets la vidéo en pause",
    "va sur l'écran 2",
    "baisse le volume à 30",
    "clique sur la première vidéo",
    "ferme Spotify",
    # « où » au milieu d'une phrase n'en fait pas une question.
    "mets-la où tu veux",
    "monte le son",
    "retiens que j'aime le thé",
    "arrête",
])
def test_une_action_n_est_pas_une_question(phrase):
    assert not deduction.est_une_question(phrase)


def test_une_action_incomprise_ne_part_pas_a_l_ia(assistant, monkeypatch):
    """
    Une action qu'ALMA n'a pas su exécuter reste une action : la confier à un
    modèle ne l'exécuterait pas davantage, et ferait attendre pour rien.
    """
    from core import ai_fallback

    appels = []

    class Bavard:
        name = "essai"

        def generate(self, query):
            appels.append(query)
            return "réponse"

    monkeypatch.setitem(ai_fallback.PROVIDERS, "essai", lambda config: Bavard())
    assistant.config.set("ai_fallback.enabled", True)
    assistant.config.set("ai_fallback.provider", "essai")
    assistant.config.set("ai_fallback.auto", "questions")

    assistant.handle("zoumbi le tralala maintenant")
    assert appels == []


def test_une_question_incomprise_part_a_l_ia(assistant, monkeypatch):
    from core import ai_fallback

    appels = []

    class Bavard:
        name = "essai"

        def generate(self, query):
            appels.append(query)
            return "Lisbonne."

    monkeypatch.setitem(ai_fallback.PROVIDERS, "essai", lambda config: Bavard())
    assistant.config.set("ai_fallback.enabled", True)
    assistant.config.set("ai_fallback.provider", "essai")
    assistant.config.set("ai_fallback.auto", "questions")

    reponse = assistant.handle("pourquoi les feuilles deviennent rouges en automne")
    assert appels == ["pourquoi les feuilles deviennent rouges en automne"]
    assert reponse.ok and reponse.text == "Lisbonne."


def test_le_reglage_jamais_coupe_tout(assistant, monkeypatch):
    from core import ai_fallback

    appels = []

    class Bavard:
        name = "essai"

        def generate(self, query):
            appels.append(query)
            return "réponse"

    monkeypatch.setitem(ai_fallback.PROVIDERS, "essai", lambda config: Bavard())
    assistant.config.set("ai_fallback.enabled", True)
    assistant.config.set("ai_fallback.provider", "essai")
    assistant.config.set("ai_fallback.auto", "jamais")

    assistant.handle("pourquoi le ciel est bleu")
    assert appels == []


def test_rien_ne_part_tant_que_le_fallback_est_eteint(assistant, monkeypatch):
    """L'interrupteur général passe avant le réglage fin."""
    from core import ai_fallback

    appels = []

    class Bavard:
        name = "essai"

        def generate(self, query):
            appels.append(query)
            return "réponse"

    monkeypatch.setitem(ai_fallback.PROVIDERS, "essai", lambda config: Bavard())
    assistant.config.set("ai_fallback.provider", "essai")
    assistant.config.set("ai_fallback.auto", "tout")

    assistant.handle("pourquoi le ciel est bleu")
    assert appels == []
