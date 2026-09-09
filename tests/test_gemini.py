"""
Poser la question à Gemini, en arrière-plan.

Rien ne s'ouvre à l'écran : pas de navigateur, pas d'onglet. ALMA interroge
l'API, reçoit du texte et le dit comme si elle répondait elle-même.

Aucun de ces tests n'appelle Gemini : la couche réseau est remplacée par un
double. Ils vérifient ce qui est promis autour — la clé n'est jamais écrite,
l'absence de clé se dit clairement, et une action ne part pas à l'IA.
"""

import os

import pytest

from core import deduction
from core.providers import gemini_provider
from core.providers.gemini_provider import GeminiProvider


class Reponse:
    """Ce que `requests.post` rend, réduit à ce que le provider en lit."""

    def __init__(self, donnees=None, status_code=200):
        self.donnees = donnees if donnees is not None else {}
        self.status_code = status_code

    def json(self):
        return self.donnees


def reponse_de(texte):
    return Reponse({"candidates": [{"content": {"parts": [{"text": texte}]}}]})


class PostEspion:
    """Retient l'appel au lieu de le faire."""

    def __init__(self, reponse=None):
        self.reponse = reponse if reponse is not None else reponse_de("Lisbonne.")
        self.appels = []

    def __call__(self, url, **kwargs):
        self.appels.append((url, kwargs))
        return self.reponse


@pytest.fixture
def avec_cle(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "cle-de-test")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)


@pytest.fixture
def sans_cle(monkeypatch):
    for variable in gemini_provider.VARIABLES_ACCEPTEES:
        monkeypatch.delenv(variable, raising=False)


def espionner(monkeypatch, reponse=None):
    import requests

    espion = PostEspion(reponse)
    monkeypatch.setattr(requests, "post", espion)
    return espion


# --------------------------------------------------------------------------
# La clé
# --------------------------------------------------------------------------
def test_sans_cle_il_le_dit_et_n_appelle_rien(config, sans_cle, monkeypatch):
    espion = espionner(monkeypatch)
    reponse = GeminiProvider(config).generate("quelle est la capitale du Portugal")
    assert "clé" in reponse.lower() and "GEMINI_API_KEY" in reponse
    assert espion.appels == [], "aucun appel ne doit partir sans clé"


def test_la_cle_ne_vient_jamais_de_la_configuration(config):
    """
    Un config.yaml se copie, se partage et se pousse par mégarde. La clé se
    lit dans l'environnement, et nulle part ailleurs.
    """
    assert "api_key" not in (config.get("ai_fallback.gemini") or {})
    assert "cle" not in (config.get("ai_fallback.gemini") or {})


def test_la_cle_n_est_jamais_ecrite(config, avec_cle, monkeypatch):
    """Même discipline que pour ANTHROPIC_API_KEY : on constate, on ne touche pas."""
    espionner(monkeypatch)
    avant = dict(os.environ)
    GeminiProvider(config).generate("bonjour")
    assert dict(os.environ) == avant


def test_l_autre_nom_de_variable_est_accepte(config, monkeypatch):
    """Google publie ses outils sous deux noms selon les époques."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "cle-de-test")
    assert GeminiProvider(config).cle() == "cle-de-test"


def test_la_cle_ne_passe_pas_par_l_url(config, avec_cle, monkeypatch):
    """Une URL se retrouve dans les journaux, les historiques et les erreurs."""
    espion = espionner(monkeypatch)
    GeminiProvider(config).generate("bonjour")
    url, kwargs = espion.appels[0]
    assert "cle-de-test" not in url
    assert kwargs["headers"]["x-goog-api-key"] == "cle-de-test"


# --------------------------------------------------------------------------
# La réponse
# --------------------------------------------------------------------------
def test_la_reponse_revient_telle_quelle(config, avec_cle, monkeypatch):
    espionner(monkeypatch, reponse_de("Lisbonne est la capitale du Portugal."))
    assert GeminiProvider(config).generate("capitale du Portugal") \
        == "Lisbonne est la capitale du Portugal."


def test_rien_ne_trahit_gemini_dans_la_reponse(config, avec_cle, monkeypatch):
    """ALMA répond ; elle ne présente pas quelqu'un d'autre."""
    espionner(monkeypatch, reponse_de("Lisbonne."))
    assert "gemini" not in GeminiProvider(config).generate("capitale ?").lower()


def test_la_consigne_demande_du_texte_dicible(config, avec_cle, monkeypatch):
    """La réponse est lue à voix haute : « **gras** » s'y entendrait."""
    import json

    espion = espionner(monkeypatch)
    GeminiProvider(config).generate("bonjour")
    corps = json.loads(espion.appels[0][1]["data"])
    consigne = corps["systemInstruction"]["parts"][0]["text"].lower()
    assert "français" in consigne
    for interdit in ("liste", "gras", "titre"):
        assert interdit in consigne
    assert corps["contents"][0]["parts"][0]["text"] == "bonjour"


@pytest.mark.parametrize("code,attendu", [
    (401, "refusée"),
    (403, "refusée"),
    (404, "modèle"),
    (429, "quota"),
])
def test_les_erreurs_sont_dites_en_clair(config, avec_cle, monkeypatch, code, attendu):
    espionner(monkeypatch, Reponse({"error": {"message": "détail"}}, status_code=code))
    assert attendu in GeminiProvider(config).generate("bonjour").lower()


def test_une_panne_de_reseau_ne_fait_pas_tomber_alma(config, avec_cle, monkeypatch):
    import requests

    def echoue(*a, **k):
        raise OSError("réseau injoignable")

    monkeypatch.setattr(requests, "post", echoue)
    reponse = GeminiProvider(config).generate("bonjour")
    assert "joindre" in reponse.lower()


def test_une_reponse_vide_ne_passe_pas_pour_une_reponse(config, avec_cle, monkeypatch):
    espionner(monkeypatch, Reponse({"candidates": []}))
    assert "rien" in GeminiProvider(config).generate("bonjour").lower()


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
