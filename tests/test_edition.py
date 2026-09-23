"""
Les deux éditions, et la frontière entre elles.

Ce fichier garde une promesse commerciale autant que technique : qui n'a rien
payé ne doit rien voir partir de sa machine, et qui a payé ne doit pas voir
partir ce que l'automatisation savait déjà faire.

Il garde aussi une décision de produit — **il n'existe qu'une seule voie vers
ALMA+, l'abonnement**. Coller sa propre clé d'API a existé, puis a été retiré
entièrement : proposer « abonnez-vous, ou bien procurez-vous une clé chez un
tiers » demande à l'utilisateur de choisir entre deux choses qu'il ne sait pas
comparer. Les tests de la fin de ce fichier interdisent son retour.

Aucun test ici n'appelle l'API. Le fixture `aucune_trace_sur_la_machine`
neutralise l'abonnement du Store ; les tests qui veulent ALMA+ posent leur
propre doublure — sans quoi la suite ferait de vrais appels facturés sur des
phrases de test.
"""

import pytest

from core import abonnement_store, ai_fallback, edition
from core.ai_fallback import NullProvider, get_provider
from core.context import Utterance


@pytest.fixture
def abonne(config, monkeypatch):
    """Une machine dont l'abonnement au Store est actif."""
    monkeypatch.setattr(abonnement_store, "abonne", lambda store_id: True)
    edition.oublier_le_cache()
    return config


# --------------------------------------------------------------------------
# Ce qui s'applique vraiment
# --------------------------------------------------------------------------
def test_par_defaut_c_est_libre(config):
    assert edition.active(config) == "libre"
    assert edition.est_complete(config) is False


def test_avec_l_abonnement_c_est_complete(abonne):
    assert edition.active(abonne) == "complete"
    assert edition.est_complete(abonne) is True


def test_le_reglage_seul_ne_suffit_pas(config):
    """
    Une configuration copiée d'une machine à l'autre ne doit pas faire croire
    à ALMA qu'elle peut appeler : chaque demande finirait en erreur au lieu
    de retomber sur ce qui marche.
    """
    config.set("general.edition", "complete")

    assert edition.souhaitee(config) == "complete"
    assert edition.active(config) == "libre"
    assert isinstance(get_provider(config), NullProvider)


def test_un_reglage_inconnu_retombe_en_libre(config):
    config.set("general.edition", "illimitée")
    assert edition.souhaitee(config) == "libre"


def test_un_store_muet_se_comporte_comme_pas_d_abonnement(config, monkeypatch):
    """
    Hors paquet, ou si le Store ne répond pas, `abonne` rend False sans
    lever. ALMA retombe en libre — qui marche sans rien — plutôt que de
    refuser de démarrer.
    """
    monkeypatch.setattr(abonnement_store, "abonne", lambda store_id: False)
    edition.oublier_le_cache()

    assert edition.est_complete(config) is False


def test_la_reponse_du_store_est_gardee_quelques_secondes(config, monkeypatch):
    """
    Interroger WinRT à chaque phrase non reconnue coûterait cinquante
    millisecondes à chaque mot.
    """
    appels = []
    monkeypatch.setattr(abonnement_store, "abonne",
                        lambda store_id: appels.append(1) or True)
    edition.oublier_le_cache()

    for _ in range(5):
        edition.est_complete(config)

    assert len(appels) == 1, appels


def test_un_achat_invalide_la_reponse_gardee(config, monkeypatch):
    """
    Sans cela, ALMA croirait l'utilisateur non abonné pendant trente secondes
    après qu'il vient de payer — la pire seconde possible pour un doute.
    """
    etats = iter([False, True])
    monkeypatch.setattr(abonnement_store, "abonne",
                        lambda store_id: next(etats))
    edition.oublier_le_cache()
    assert edition.est_complete(config) is False

    edition.oublier_le_cache()

    assert edition.est_complete(config) is True


# --------------------------------------------------------------------------
# Le provider qui en découle
# --------------------------------------------------------------------------
def test_sans_abonnement_aucun_provider(config):
    assert isinstance(get_provider(config), NullProvider)


def test_avec_l_abonnement_le_provider_claude(abonne):
    assert get_provider(abonne).name == "claude_api"


def test_l_abonnement_passe_avant_le_reglage_avance(abonne):
    """
    Un utilisateur avancé peut avoir laissé Ollama configuré. L'abonnement
    qu'il paie l'emporte : c'est ce qu'il a choisi en dernier.
    """
    abonne.set("ai_fallback.enabled", True)
    abonne.set("ai_fallback.provider", "ollama")

    assert get_provider(abonne).name == "claude_api"


def test_l_echappatoire_locale_survit_en_edition_libre(config):
    """
    Ollama reste joignable sans abonnement : il tourne sur la machine, il ne
    coûte rien, et il est désactivé par défaut. Ce n'est pas le produit,
    c'est un réglage avancé — et le retirer punirait ceux qui l'utilisent.
    """
    config.set("ai_fallback.enabled", True)
    config.set("ai_fallback.provider", "ollama")

    assert get_provider(config).name == "ollama"


def test_le_provider_passe_par_le_relais_et_ne_detient_aucune_cle(abonne,
                                                                  monkeypatch):
    """
    Le cœur du dispositif : l'application envoie un JETON signé par Microsoft
    là où elle mettrait une clé, et c'est le relais qui détient celle-ci.
    """
    from core.providers.claude_api_provider import ClaudeApiProvider

    monkeypatch.setattr(abonnement_store, "jeton",
                        lambda audience="": "jeton-signe")
    abonne.set("abonnement.relais_url", "https://relais.test")

    construits = []
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **k: construits.append(k) or object())

    ClaudeApiProvider(abonne).client()

    assert construits[0]["base_url"] == "https://relais.test"
    assert construits[0]["api_key"] == "jeton-signe"
    assert not construits[0]["api_key"].startswith("sk-ant")


def test_un_abonnement_sans_relais_le_dit_clairement(abonne):
    """
    Le cas qui arrivera pendant le déploiement : abonné, mais le relais n'est
    pas encore en ligne. Le message doit le dire, pas ressembler à un
    problème d'abonnement.
    """
    from core.providers.claude_api_provider import ClaudeApiProvider

    abonne.set("abonnement.relais_url", "")

    with pytest.raises(RuntimeError, match="relais"):
        ClaudeApiProvider(abonne).client()


# --------------------------------------------------------------------------
# Ce qu'on répond à qui demande plus que l'automatisation
# --------------------------------------------------------------------------
def enonce(phrase, langue="fr"):
    utterance = Utterance.parse(phrase, wake_words=["alma"])
    assert utterance.lang == langue, (phrase, utterance.lang)
    return utterance


def test_une_question_en_libre_recoit_une_explication_pas_un_echec(assistant):
    """
    « Je n'ai pas compris » serait FAUX : ALMA a très bien compris, elle ne
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
    est un vrai malentendu, et lui répondre « prenez ALMA+ » serait une
    réclame déplacée autant qu'un mensonge.
    """
    reponse = ai_fallback.handle_unmatched(enonce("brzzt kkrr tchac"), assistant)

    assert reponse.text in ai_fallback.SUGGESTIONS


# --------------------------------------------------------------------------
# L'ordre : l'automatisation d'abord, toujours
# --------------------------------------------------------------------------
def test_une_commande_connue_ne_passe_jamais_par_le_modele(abonne, assistant,
                                                           monkeypatch):
    """
    LA règle d'ALMA+ : ce que le routeur sait faire, il le fait. Le modèle
    coûte de l'argent et fait attendre une seconde et demie ; passer par lui
    pour « quelle heure est-il » serait payer pour être plus lent.
    """
    appels = []
    monkeypatch.setattr(ai_fallback, "handle_with_ai",
                        lambda *a, **k: appels.append(a) or "réponse du modèle")

    assistant.handle("quelle heure est-il")
    assistant.handle("prends une photo")

    assert appels == [], "une commande déclarée est partie au modèle"


# --------------------------------------------------------------------------
# Aucune clé d'API, nulle part — et pas même l'idée
# --------------------------------------------------------------------------
# Ces tests gardent une décision de produit, pas un détail technique. Il n'y
# a qu'une voie vers ALMA+ : l'abonnement. Tout ce qui permettait d'en coller
# une a été retiré, et doit le rester.

def test_le_module_edition_n_offre_aucun_moyen_de_poser_une_cle():
    interdits = [nom for nom in dir(edition)
                 if "cle" in nom.lower() or "key" in nom.lower()]
    assert interdits == [], interdits


def test_aucun_module_ne_range_de_cle():
    """Le coffre a été supprimé : rien ne doit le ressusciter."""
    import importlib

    with pytest.raises(ImportError):
        importlib.import_module("core.secrets")


def test_aucune_cle_n_est_lue_dans_l_environnement(monkeypatch, config):
    """
    ALMA ne se sert QUE de l'abonnement. Une clé qui traîne dans
    l'environnement — celle d'un autre outil, celle d'un développeur — ne
    doit rien activer.
    """
    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                     "CLAUDE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(variable, "sk-ant-ceci-ne-doit-rien-activer")
    edition.oublier_le_cache()

    assert edition.est_complete(config) is False
    assert isinstance(get_provider(config), NullProvider)


def test_aucune_cle_ne_peut_se_ranger_dans_les_preferences(config):
    from core.preferences import CATALOGUE

    assert "api_key" not in (config.get("ai_fallback") or {})
    assert not any("key" in reglage.chemin.lower() or "cle" in reglage.chemin.lower()
                   for reglage in CATALOGUE)


def test_la_liste_des_providers_reste_close():
    assert set(ai_fallback.PROVIDERS) == {"none", "ollama", "claude_api",
                                          "claude_code"}
