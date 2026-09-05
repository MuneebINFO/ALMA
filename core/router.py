"""
Moteur de routage d intentions.

Aucune IA ici : uniquement du pattern matching (regex) puis, en filet de
securite, un score sur mots-cles tolerant aux fautes de frappe.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from core import text_utils
from core.context import CommandContext, Response, Utterance
from core.registry import Command, all_commands

log = logging.getLogger(__name__)


@dataclass
class Resolution:
    """Resultat de la resolution : quelle commande, avec quel match regex."""

    command: Command
    match: re.Match | None = None
    score: float = 0.0
    via: str = "regex"


class Router:
    """Associe une phrase a une commande, puis l execute."""

    def __init__(self, commands: list | None = None) -> None:
        self._commands = commands

    @property
    def commands(self) -> list:
        return self._commands if self._commands is not None else all_commands()

    def resolve(self, utterance: Utterance, assistant=None) -> Resolution | None:
        """
        Retourne la commande correspondante SANS l executer.
        Expose separement de dispatch() pour pouvoir la tester unitairement.
        """
        if utterance.is_empty():
            return None

        candidates = [c for c in self.commands if c.accepts_source(utterance.source)]

        # Passe 1 : regex, par priorite decroissante.
        for cmd in candidates:
            for pattern in cmd.patterns:
                match = pattern.search(utterance.norm)
                if not match:
                    continue
                if not self._guard_ok(cmd, utterance, match, assistant):
                    continue
                return Resolution(cmd, match, float(cmd.priority), "regex")

        # Passe 2 : mots-cles avec tolerance aux fautes de frappe.
        best: Resolution | None = None
        for cmd in candidates:
            for group in cmd.keywords:
                if not group:
                    continue
                if all(text_utils.fuzzy_in(word, utterance.tokens) for word in group):
                    score = cmd.priority + 2 * len(group)
                    if (best is None or score > best.score) and self._guard_ok(
                        cmd, utterance, None, assistant
                    ):
                        best = Resolution(cmd, None, score, "keywords")
        return best

    def _guard_ok(self, cmd: Command, utterance: Utterance, match, assistant) -> bool:
        """Evalue le guard optionnel d'une commande."""
        if cmd.guard is None:
            return True
        # L assistant peut être absent (tests) : le contexte retombe alors sur
        # la configuration par defaut, donc le guard reste evaluable.
        ctx = CommandContext(utterance, assistant, match=match, command=cmd)
        try:
            return bool(cmd.guard(ctx))
        except Exception:
            log.exception("Le guard de la commande %s a echoue", cmd.name)
            return False

    def dispatch(self, utterance: Utterance, assistant) -> Response:
        """Resout puis execute. Renvoie toujours une Response."""
        return self.run(utterance, assistant)[0]

    def run(self, utterance: Utterance, assistant):
        """
        Resout puis execute, en renvoyant (Response, Resolution).
        La resolution n est faite QU UNE FOIS (les guards ne sont pas rejoues).
        """
        resolution = self.resolve(utterance, assistant)
        if resolution is None:
            from core.ai_fallback import handle_unmatched

            return handle_unmatched(utterance, assistant), None

        ctx = CommandContext(
            utterance, assistant, match=resolution.match, command=resolution.command
        )
        try:
            result = resolution.command.handler(ctx)
        except Exception as exc:
            log.exception("Erreur dans la commande %s", resolution.command.name)
            return (
                Response.error(
                    "Une erreur est survenue en exécutant la commande "
                    + resolution.command.name
                    + " : "
                    + str(exc)
                ),
                resolution,
            )
        if result is None:
            return Response(text="", speak=False), resolution
        if isinstance(result, str):
            return Response(text=result), resolution
        return result, resolution
