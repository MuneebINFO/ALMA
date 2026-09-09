"""
« 15 x 4 » : la multiplication telle qu'on l'écrit et qu'on la dicte.

Le défaut constaté à l'usage : « combien font 15 x 4 » n'était pas reconnu
comme un calcul, partait à l'IA, et revenait avec l'avertissement de bas de
page de Google. Un calcul doit rester local, immédiat et exact.
"""

import pytest

from core.context import Utterance


def commande(assistant, phrase):
    resolution = assistant.router.resolve(
        Utterance.parse(phrase, wake_words=assistant.config.get("general.wake_words")),
        assistant=assistant,
    )
    return resolution.command.name if resolution else "aucune"


@pytest.mark.parametrize("phrase,resultat", [
    ("combien font 15 x 4", "60"),
    ("15 x 4", "60"),
    ("calcule 12 x 3", "36"),
    ("8 x 8", "64"),
    ("combien font 100 x 0", "0"),
    # Ce qui marchait déjà doit continuer.
    ("combien font 15 fois 4", "60"),
    ("calcule 12 plus 7", "19"),
])
def test_la_multiplication_se_dit_aussi_avec_un_x(assistant, phrase, resultat):
    reponse = assistant.handle(phrase)
    assert reponse.ok, phrase + " : " + reponse.text
    assert resultat in reponse.text


def test_un_calcul_ne_part_jamais_a_l_ia(assistant, monkeypatch):
    """C'est tout l'objet de la correction : rien ne doit sortir de la machine."""
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

    assert "60" in assistant.handle("combien font 15 x 4").text
    assert appels == []


@pytest.mark.parametrize("phrase,attendu", [
    # « x » sert aussi de nom d'exemple : le garde-fou doit tenir.
    ("ouvre X", "open_website"),
    ("va sur X", "open_website"),
    ("clique sur X", "cliquer_sur"),
    ("ouvre Chrome", "open_app"),
    ("va sur l'écran 2", "choisir_ecran"),
    ("ferme Spotify", "close_app"),
])
def test_un_x_isole_ne_transforme_pas_tout_en_calcul(assistant, phrase, attendu):
    assert commande(assistant, phrase) == attendu
