"""
Point d extension IA (facade "provider") -- DESACTIVE PAR DEFAUT.

Etat par defaut (ai_fallback.enabled = false) : quand aucune commande locale ne
correspond, on repond poliment et on suggere "aide".
AUCUN appel reseau, AUCUN sous-processus, AUCUN cout.

Quand il est active, le fallback delegue la requete au CLI Claude Code deja
installe sur la machine (voir core/providers/claude_code_provider.py). C est la
SEULE porte d entree IA du projet : il n existe aucun autre canal vers une API.

Pour l activer, dans config.yaml :
    ai_fallback:
      enabled: true
      provider: claude_code
      claude_code:
        working_dir: C:/chemin/vers/un/dossier   # obligatoire
"""

from __future__ import annotations

import random

from core.context import Response, Utterance
from core.providers import AIProvider  # interface partagee par tous les providers

SUGGESTIONS = [
    "Je n'ai pas compris cette demande. Dites « aide » pour voir ce que je sais faire.",
    "Désolé, cette commande ne fait pas partie de mon répertoire. Essayez « que peux-tu faire ».",
    "Je ne sais pas encore faire cela. Tapez « aide » pour la liste des commandes.",
]


class NullProvider:
    """Provider par defaut : aucune IA, aucun reseau, aucun sous-processus."""

    name = "none"

    def generate(self, query: str) -> str:
        return random.choice(SUGGESTIONS)


def _claude_code_factory(config):
    """Import paresseux : le module n est charge que si le provider est demande."""
    from core.providers.claude_code_provider import ClaudeCodeProvider

    return ClaudeCodeProvider(config)


# Registre des providers. Pour en ajouter un : creer un module dans
# core/providers/ puis ajouter une entree ici. Rien d autre ne change.
PROVIDERS = {
    "none": lambda config: NullProvider(),
    "claude_code": _claude_code_factory,
}


def get_provider(config) -> AIProvider:
    """
    Retourne le provider configure.

    Renvoie NullProvider des que le fallback est desactive : c est ce qui
    garantit qu aucun appel externe ne part tant que enabled vaut false.
    """
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


def handle_with_ai(query: str, config=None) -> str:
    """
    Interface stable appelee quand aucune commande locale ne correspond.
    Par defaut : message poli, sans aucun appel exterieur.
    """
    provider = get_provider(config)
    try:
        return provider.generate(query)
    except NotImplementedError as exc:
        return "Le mode IA est activé mais le provider n'est pas implémenté. " + str(exc)
    except Exception as exc:
        return (
            "Le provider IA a échoué (" + str(exc) + "). Dites « aide » pour les commandes locales."
        )


def handle_unmatched(utterance: Utterance, assistant=None) -> Response:
    """Appele par le routeur lorsqu aucune regle ne matche."""
    config = getattr(assistant, "config", None)
    return Response(text=handle_with_ai(utterance.raw, config), ok=False)
