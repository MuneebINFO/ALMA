"""
Point d extension IA (facade "provider") -- DESACTIVE PAR DEFAUT.

Etat par defaut (ai_fallback.enabled = false) : quand aucune commande locale ne
correspond, on repond poliment et on suggere "aide".
AUCUN appel reseau, AUCUN sous-processus, AUCUN cout.

Quand il est active, deux providers existent, et aucun autre canal vers une
IA n existe dans le projet :

  - ollama : un modele de langage qui tourne SUR LA MACHINE. Aucun compte,
    aucune cle, rien qui sorte de l ordinateur. Il REPOND seulement -- il
    n execute aucune action, le corps d Alma reste le moteur de regles ;
  - claude_code : delegation au CLI Claude Code deja installe.

Pour l activer, dans config.yaml :
    ai_fallback:
      enabled: true
      provider: ollama              # ou claude_code
      ollama:
        modele: qwen2.5:3b          # telecharge par « ollama pull »
"""

from __future__ import annotations

import logging
import random

from core import text_utils
from core.context import Response, Utterance
from core.providers import AIProvider  # interface partagee par tous les providers

log = logging.getLogger(__name__)

# Reponses quand rien n est compris : courtes et sans renvoi vers l aide.
# Une phrase longue coupe le rythme et n apprend rien a qui utilise
# l assistant tous les jours.
SUGGESTIONS = [
    "Je n'ai pas compris.",
    "Désolé, je n'ai pas saisi.",
    "Pardon ?",
]

# Les memes, pour qui parle anglais. Ce ne sont pas des traductions mot a
# mot : ce sont les formules courtes qu on emploie dans cette langue.
SUGGESTIONS_EN = [
    "I didn't catch that.",
    "Sorry, I didn't get that.",
    "Pardon?",
]


class NullProvider:
    """Provider par defaut : aucune IA, aucun reseau, aucun sous-processus."""

    name = "none"

    def generate(self, query: str) -> str:
        return random.choice(SUGGESTIONS)


def _ollama_factory(config):
    """Import paresseux : le module n est charge que si le provider est demande."""
    from core.providers.ollama_provider import OllamaProvider

    return OllamaProvider(config)


def _claude_api_factory(config):
    """Import paresseux : le module n est charge que si le provider est demande."""
    from core.providers.claude_api_provider import ClaudeApiProvider

    return ClaudeApiProvider(config)


def _claude_code_factory(config):
    """Import paresseux : le module n est charge que si le provider est demande."""
    from core.providers.claude_code_provider import ClaudeCodeProvider

    return ClaudeCodeProvider(config)


# Registre des providers. Pour en ajouter un : creer un module dans
# core/providers/ puis ajouter une entree ici. Rien d autre ne change.
PROVIDERS = {
    "none": lambda config: NullProvider(),
    "ollama": _ollama_factory,
    "claude_api": _claude_api_factory,
    "claude_code": _claude_code_factory,
}


def get_provider(config) -> AIProvider:
    """
    Retourne le provider configure.

    Renvoie NullProvider des que le fallback est desactive : c est ce qui
    garantit qu aucun appel externe ne part tant que enabled vaut false.
    """
    # L EDITION D ABORD. Une cle posee par l utilisateur vaut activation : on
    # ne va pas lui demander de cocher en plus une case dans un fichier qu il
    # n ouvrira jamais. `ai_fallback` reste en dessous -- c est l echappatoire
    # des utilisateurs avances (un modele local, le CLI Claude Code), pas le
    # produit.
    from core import edition

    if edition.est_complete(config):
        try:
            return _claude_api_factory(config)
        except Exception as exc:
            log.warning("Édition complète indisponible : %s", exc)
            return NullProvider()

    if not config or not config.get("ai_fallback.enabled", False):
        return NullProvider()
    name = str(config.get("ai_fallback.provider", "none") or "none").lower()
    factory = PROVIDERS.get(name)
    if factory is None:
        return NullProvider()
    try:
        return factory(config)
    except Exception:
        return NullProvider()


def handle_with_ai(query: str, config=None, provider=None) -> str:
    """
    Interface stable appelee quand aucune commande locale ne correspond.
    Par defaut : message poli, sans aucun appel exterieur.

    `provider` evite de le reconstruire quand l appelant l a deja sous la main.
    """
    provider = provider if provider is not None else get_provider(config)
    try:
        # Une reponse de modele est ecrite en Markdown. Elle est lue a voix
        # haute : « **1 seul fichier** » se dirait « asterisque asterisque ».
        return text_utils.sans_balisage(provider.generate(query))
    except NotImplementedError as exc:
        return "Le mode IA est activé mais le provider n'est pas implémenté. " + str(exc)
    except Exception as exc:
        return (
            "Le provider IA a échoué (" + str(exc) + "). Dites « aide » pour les commandes locales."
        )


def handle_unmatched(utterance: Utterance, assistant=None) -> Response:
    """
    Appele par le routeur lorsqu aucune regle ne matche.

    Avant de renoncer, on tente de DEDUIRE ce qui a ete voulu : la
    transcription a pu deformer un mot, ou le reste de la phrase suffit a
    reconstruire l intention. Ce n est tente qu ici, donc uniquement sur des
    demandes qui nous etaient bien adressees.
    """
    config = getattr(assistant, "config", None)

    if assistant is not None:
        deduit = _tenter_deduction(utterance, assistant)
        if deduit is not None:
            return deduit

    langue = getattr(utterance, "lang", "fr")

    if not delegation_automatique(config, utterance.raw):
        # Une QUESTION restee sans reponse en edition libre n est pas un
        # malentendu : Alma a tres bien compris, elle ne fait simplement pas
        # ca. Lui repondre « je n ai pas compris » serait faux, et laisserait
        # croire a un defaut de reconnaissance vocale -- on cherche alors un
        # probleme la ou il n y en a pas.
        from core import deduction, edition

        if not edition.est_complete(config) and deduction.est_une_question(utterance.raw):
            return Response(text=edition.hors_portee(langue), ok=False)
        return Response(
            text=random.choice(SUGGESTIONS_EN if langue == "en" else SUGGESTIONS),
            ok=False,
        )

    # ok=False signale « je n ai pas compris » : c est vrai tant qu aucun
    # provider ne repond, faux des qu un provider a REPONDU quelque chose.
    # Marquer une vraie reponse comme un echec la ferait afficher en rouge et
    # comptabiliser comme une commande ratee dans l historique.
    provider = get_provider(config)
    # C est le chemin le plus lent de l application -- une fenetre de
    # recherche ouverte, lue, refermee -- et il n est pas declare par une
    # commande : l annonce se fait donc ici.
    if assistant is not None and not isinstance(provider, NullProvider):
        try:
            genre = "reflexion" if provider.name == "claude_api" else "recherche"
            assistant.annoncer_attente(genre, langue)
        except Exception:                     # pragma: no cover - defensif
            pass
    reponse = handle_with_ai(utterance.raw, config, provider)
    return Response(text=reponse, ok=not isinstance(provider, NullProvider))


AUTO_JAMAIS = "jamais"
AUTO_QUESTIONS = "questions"
AUTO_TOUT = "tout"
AUTO_PAR_DEFAUT = AUTO_QUESTIONS


def delegation_automatique(config, texte: str = "") -> bool:
    """
    Cette phrase incomprise doit-elle partir d elle-meme au provider ?

    Trois reglages, par ai_fallback.auto :

      - « questions » (defaut) : seules les demandes qui attendent une REPONSE
        sont transmises. C est le partage naturel -- une action qu Alma n a pas
        su executer reste une action, et la confier a un modele ne l executerait
        pas davantage : cela ferait attendre pour rien, et c est ainsi qu un
        calcul mal formule ouvrait une session pour rien ;
      - « jamais » : plus rien ne part tout seul, il faut le demander
        (« demande a Claude Code de... ») ;
      - « tout » : toute phrase sans commande est rattrapee.
    """
    from core import edition

    # En edition complete, l agent rattrape TOUT ce que le routeur a laisse
    # passer -- pas seulement les questions. Une action mal formulee est
    # justement ce qu il sait rattraper : lui, il comprend « tu peux allumer
    # le truc pour me voir » et appelle la bonne commande. C est la difference
    # qu on vend, et la brider ici la supprimerait.
    if edition.est_complete(config):
        return True

    if not config or not config.get("ai_fallback.enabled", False):
        return False
    reglage = str(config.get("ai_fallback.auto", AUTO_PAR_DEFAUT)
                  or AUTO_PAR_DEFAUT).strip().lower()
    if reglage == AUTO_TOUT:
        return True
    if reglage == AUTO_QUESTIONS:
        from core import deduction

        return deduction.est_une_question(texte)
    return False


def _tenter_deduction(utterance: Utterance, assistant):
    """Reconstruit puis execute la demande, si l on parvient a la deduire."""
    from core import deduction
    from core.context import Utterance as Enonce

    wake_words = assistant.config.get("general.wake_words")

    def resout(phrase: str) -> bool:
        essai = Enonce.parse(phrase, source=utterance.source, wake_words=wake_words)
        if essai.is_empty():
            return False
        try:
            return assistant.router.resolve(essai, assistant) is not None
        except Exception:
            return False

    try:
        phrase = deduction.deduire(utterance.raw, resout)
    except Exception:
        return None
    if not phrase:
        return None

    essai = Enonce.parse(phrase, source=utterance.source, wake_words=wake_words)
    resolution = assistant.router.resolve(essai, assistant)
    if resolution is None:
        return None
    from core.context import CommandContext

    ctx = CommandContext(essai, assistant, match=resolution.match, command=resolution.command)
    try:
        resultat = resolution.command.handler(ctx)
    except Exception:
        return None
    if isinstance(resultat, str):
        return Response(text=resultat)
    return resultat
