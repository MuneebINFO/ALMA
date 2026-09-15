"""
Les deux éditions, et la frontière entre elles.

Ce fichier garde une promesse commerciale autant que technique : qui n'a rien
payé ne doit rien voir partir de sa machine, et qui a payé ne doit pas voir
partir ce que l'automatisation savait déjà faire.

Aucun test ici n'appelle l'API. Le fixture `aucune_trace_sur_la_machine` rend
le coffre vide ; les tests qui veulent l'édition complète posent une fausse
clé et un faux provider par-dessus — sans quoi la suite se mettrait à faire
de vrais appels facturés sur des phrases de test.
"""

import pytest

from core import ai_fallback, edition, secrets
from core.ai_fallback import NullProvider, get_provider
from core.context import Utterance


@pytest.fixture
def edition_complete(config, monkeypatch):
    """Une machine où l'utilisateur a posé sa clé."""
    monkeypatch.setattr(secrets, "lire",
                        lambda nom, cfg=None: "sk-ant-fausse-cle" if nom == edition.CLE_API else "")
    config.set("general.edition", "complete")
    return config


# --------------------------------------------------------------------------
# Ce qui s'applique vraiment
# --------------------------------------------------------------------------
def test_par_defaut_c_est_libre(config):
    assert edition.souhaitee(config) == "libre"
    assert edition.active(config) == "libre"
    assert edition.est_complete(config) is False


def test_avec_la_cle_c_est_complete(edition_complete):
    assert edition.active(edition_complete) == "complete"
    assert edition.est_complete(edition_complete) is True


def test_la_cle_sans_le_reglage_ne_suffit_pas(config, monkeypatch):
    """
    Une clé oubliée dans le coffre ne rallume pas l'édition complète toute
    seule : l'utilisateur qui est repassé en libre a pris une décision, et
    elle doit tenir.
    """
    monkeypatch.setattr(secrets, "lire", lambda nom, cfg=None: "sk-ant-fausse-cle")
    config.set("general.edition", "libre")

    assert edition.est_complete(config) is False


def test_un_reglage_inconnu_retombe_en_libre(config):
    """Une configuration bricolée à la main ne doit pas ouvrir de porte."""
    config.set("general.edition", "illimitée")
    assert edition.souhaitee(config) == "libre"


def test_un_coffre_illisible_se_comporte_comme_un_coffre_vide(config, monkeypatch):
    """
    Coffre posé sous un autre compte Windows, fichier abîmé : `lire` rend une
    chaîne vide au lieu de lever. Alma retombe en libre — qui marche sans
    rien — plutôt que de refuser de démarrer.
    """
    def illisible(nom, cfg=None):
        raise OSError("fichier abîmé")

    monkeypatch.setattr(secrets, "_charger", illisible)
    config.set("general.edition", "complete")

    with pytest.raises(OSError):
        secrets._charger(config)          # la doublure fait bien ce qu'on croit
    assert edition.cle(config) == ""
    assert edition.est_complete(config) is False


# --------------------------------------------------------------------------
# Le provider qui en découle
# --------------------------------------------------------------------------
def test_sans_cle_aucun_provider(config):
    assert isinstance(get_provider(config), NullProvider)


def test_avec_la_cle_le_provider_claude(edition_complete):
    provider = get_provider(edition_complete)
    assert provider.name == "claude_api"


def test_l_edition_passe_avant_le_reglage_avance(edition_complete):
    """
    Un utilisateur avancé peut avoir laissé Ollama configuré. La clé qu'il
    vient de poser doit l'emporter : c'est ce qu'il a choisi en dernier, et
    c'est ce qu'il paie.
    """
    edition_complete.set("ai_fallback.enabled", True)
    edition_complete.set("ai_fallback.provider", "ollama")

    assert get_provider(edition_complete).name == "claude_api"


def test_l_echappatoire_locale_survit_en_edition_libre(config):
    """
    Ollama reste joignable sans clé : il tourne sur la machine, il ne coûte
    rien, et il est désactivé par défaut. Ce n'est pas le produit, c'est un
    réglage avancé — et le retirer punirait ceux qui l'utilisent.
    """
    config.set("ai_fallback.enabled", True)
    config.set("ai_fallback.provider", "ollama")

    assert get_provider(config).name == "ollama"


# --------------------------------------------------------------------------
# Ce qu'on répond à qui demande plus que l'automatisation
# --------------------------------------------------------------------------
def enonce(phrase, langue="fr"):
    utterance = Utterance.parse(phrase, wake_words=["alma"])
    assert utterance.lang == langue, (phrase, utterance.lang)
    return utterance


def test_une_question_en_libre_recoit_une_explication_pas_un_echec(assistant):
    """
    « Je n'ai pas compris » serait FAUX : Alma a très bien compris, elle ne
    fait simplement pas ça. Laisser croire à un défaut de reconnaissance
    vocale enverrait l'utilisateur chercher un problème de micro inexistant.
    """
    reponse = ai_fallback.handle_unmatched(
        enonce("pourquoi le ciel est bleu"), assistant)

    assert reponse.text == edition.HORS_PORTEE_FR
    assert reponse.text not in ai_fallback.SUGGESTIONS


def test_la_meme_chose_en_anglais(assistant):
    reponse = ai_fallback.handle_unmatched(
        enonce("why is the sky blue", "en"), assistant)

    assert reponse.text == edition.HORS_PORTEE_EN


def test_une_phrase_incomprise_reste_incomprise(assistant):
    """
    L'explication ne vaut que pour les QUESTIONS. Une commande mal entendue
    est un vrai malentendu, et lui répondre « prenez l'édition complète »
    serait une réclame déplacée autant qu'un mensonge.
    """
    reponse = ai_fallback.handle_unmatched(enonce("brzzt kkrr tchac"), assistant)

    assert reponse.text in ai_fallback.SUGGESTIONS
    assert reponse.text != edition.HORS_PORTEE_FR


# --------------------------------------------------------------------------
# L'ordre : l'automatisation d'abord, toujours
# --------------------------------------------------------------------------
def test_une_commande_connue_ne_passe_jamais_par_le_modele(edition_complete,
                                                           assistant, monkeypatch):
    """
    LA règle de l'édition complète : ce que le routeur sait faire, il le fait.
    Le modèle coûte de l'argent et fait attendre une seconde et demie ; passer
    par lui pour « quelle heure est-il » serait payer pour être plus lent.
    """
    appels = []
    monkeypatch.setattr(ai_fallback, "handle_with_ai",
                        lambda *a, **k: appels.append(a) or "réponse du modèle")

    assistant.handle("quelle heure est-il")
    assistant.handle("prends une photo")

    assert appels == [], "une commande déclarée est partie au modèle"
