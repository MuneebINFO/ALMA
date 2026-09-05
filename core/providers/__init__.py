"""
Providers IA interchangeables.

Un provider est un objet respectant une interface unique et stable :

    class MonProvider:
        name = "mon_provider"
        def generate(self, query: str) -> str: ...

Pour en ajouter un : creer un module ici, puis declarer la classe dans
PROVIDERS (core/ai_fallback.py). Rien d autre dans le projet ne change.

Aujourd hui, le seul provider reel est ClaudeCodeProvider : il delegue au CLI
Claude Code deja installe sur la machine. C est la SEULE porte d entree IA du
projet -- aucun autre canal vers une API n existe.
"""

from __future__ import annotations

from typing import Protocol


class AIProvider(Protocol):
    """Interface que tout provider doit respecter."""

    name: str

    def generate(self, query: str) -> str:
        """Retourne une reponse en texte libre pour la requete donnee."""
        ...


__all__ = ["AIProvider", "ClaudeCodeProvider"]


def __getattr__(name: str):
    """Import paresseux : ne charge le provider que s il est reellement demande."""
    if name == "ClaudeCodeProvider":
        from core.providers.claude_code_provider import ClaudeCodeProvider

        return ClaudeCodeProvider
    raise AttributeError(name)
