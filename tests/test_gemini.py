"""
Poser la question à l'IA de Google, par le navigateur, en arrière-plan.

Aucune API, aucune clé : la réponse de Gemini est déjà sur google.com, sous
« Aperçu IA ». ALMA ouvre la recherche dans une fenêtre qu'elle réduit
aussitôt, la lit comme n'importe quelle page, puis la referme.

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


# Ce que la page expose vraiment, mesuré sur google.com : l'ancre, puis des
# libellés d'interface, puis la réponse, puis les sources et une fiche.
PAGE_REELLE = (
    "Recherche Google",
    "Aperçu IA",
    "À propos de ce résultat",
    "Le roman Les Misérables a été écrit par Victor Hugo et publié en 1862.",
    "Wikipédia - Les Misérables - Wikipédia. Résultats associés",
    "￼",
    "Wikipédia",
    "À propos de l'œuvre",
    "• Date de parution : 1862",
    "• Durée d'écriture : Environ 17 ans (commencé en 1845)",
    "Les Misérables - Wikipédia. S'ouvre dans un nouvel onglet.",
)

REPONSE = "Le roman Les Misérables a été écrit par Victor Hugo et publié en 1862."


# --------------------------------------------------------------------------
# Lire la réponse dans la page
# --------------------------------------------------------------------------
def test_la_reponse_est_la_premiere_phrase_apres_l_ancre(lecture):
    lecture(*PAGE_REELLE)
    assert gemini_provider.apercu(None) == REPONSE


def test_les_libelles_d_interface_ne_sont_pas_pris_pour_la_reponse(lecture):
    """« À propos de ce résultat » précède la réponse dans la vraie page."""
    lecture(*PAGE_REELLE)
    assert "propos de ce résultat" not in gemini_provider.apercu(None)


def test_ce_qui_precede_l_ancre_est_ignore(lecture):
    """Sans cela, le titre de la page passerait pour une réponse."""
    lecture(*PAGE_REELLE)
    assert "Recherche Google" not in gemini_provider.apercu(None)


def test_les_sources_et_la_fiche_ne_sont_pas_lues(lecture):
    """Écrites, elles se parcourent ; dites, elles se subissent."""
    lecture(*PAGE_REELLE)
    reponse = gemini_provider.apercu(None)
    assert "Wikipédia" not in reponse and "Date de parution" not in reponse


def test_les_images_ne_sont_pas_lues(lecture):
    """U+FFFC remplace les images dans le texte de l'accessibilité."""
    lecture("Aperçu IA", "￼",
            "Les abeilles vivent de trois à six semaines en été.")
    assert gemini_provider.apercu(None) == (
        "Les abeilles vivent de trois à six semaines en été."
    )


def test_une_reponse_courte_est_gardee_si_elle_se_termine(lecture):
    """« Victor Hugo. » est court, mais c'est une phrase."""
    lecture("Aperçu IA", "À propos de ce résultat", "Victor Hugo.")
    assert gemini_provider.apercu(None) == "Victor Hugo."


def test_sans_apercu_on_ne_rend_rien(lecture):
    """Google n'en propose pas toujours : mieux vaut rien qu'un titre de site."""
    lecture("Recherche Google", "Résultats",
            "Wikipédia — Les Misérables, roman de Victor Hugo")
    assert gemini_provider.apercu(None) == ""


def test_l_ancre_anglaise_est_reconnue(lecture):
    lecture("AI overview",
            "The sky is blue because molecules scatter sunlight unevenly.")
    assert gemini_provider.apercu(None).startswith("The sky is blue")


# --------------------------------------------------------------------------
# Ce que le provider promet autour
# --------------------------------------------------------------------------
def test_aucune_cle_n_est_demandee():
    """C'est tout l'intérêt : la page suffit."""
    from pathlib import Path

    source = Path(gemini_provider.__file__).read_text(encoding="utf-8")
    for interdit in ("API_KEY", "api_key", "googleapis.com"):
        assert interdit not in source


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

    monkeypatch.setattr(gemini_provider, "_attendre_l_apercu", echoue)
    reponse = GeminiProvider(config).generate("pourquoi le ciel est bleu")
    assert fermees == ["la-fenetre"]
    assert "pas trouvé" in reponse


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
