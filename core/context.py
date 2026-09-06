"""
Objets echanges entre le routeur et les handlers de commandes.

`Utterance` porte la phrase (brute + normalisee) et sa SOURCE ("text", "voice",
"gesture"...). C'est ce champ qui permettra de brancher plus tard'un module
camera/gestes sur exactement le meme routeur, sans dupliquer la logique metier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from core import text_utils

if TYPE_CHECKING:  # pragma: no cover - uniquement pour les type hints
    from core.assistant import Assistant

# Sources d'entree connues. "gesture" est deja reserve pour l'extension camera.
SOURCE_TEXT = "text"
SOURCE_VOICE = "voice"
SOURCE_GESTURE = "gesture"


@dataclass
class Utterance:
    """Une demande utilisateur, quelle que soit sa provenance."""

    raw: str
    norm: str
    tokens: list[str] = field(default_factory=list)
    source: str = SOURCE_TEXT

    @classmethod
    def parse(cls, text: str, source: str = SOURCE_TEXT, wake_words=None) -> "Utterance":
        raw = text.strip()
        norm = text_utils.normalize(raw)
        wake = wake_words if wake_words is not None else text_utils.DEFAULT_WAKE_WORDS
        raw, norm = text_utils.strip_wake_word(raw, norm, wake)
        raw, norm = raw.strip(), norm.strip()
        # strip() peut desaligner si raw et norm n'ont pas les memes bords ;
        # on repart donc de la version non rognee pour garder l'alignement.
        raw_full, norm_full = text_utils.strip_wake_word(
            text.strip(), text_utils.normalize(text.strip()), wake
        )
        lead = len(norm_full) - len(norm_full.lstrip())
        raw = raw_full[lead : lead + len(norm)]
        return cls(raw=raw, norm=norm, tokens=text_utils.tokenize(norm), source=source)

    def is_empty(self) -> bool:
        return not self.norm.strip()


@dataclass
class Response:
    """Ce qu'une commande renvoie a l'assistant."""

    text: str = ""
    speak: bool = True          # False = affiche mais ne lit pas a voix haute
    should_exit: bool = False   # True = quitte proprement l'application
    ok: bool = True
    data: Any = None

    @classmethod
    def error(cls, text: str) -> "Response":
        return cls(text=text, ok=False)


class CommandContext:
    """
    Contexte passe a chaque handler : l'enonce, le resultat du regex, et un
    acces a l'assistant (config, stockage, entrées/sorties, historique).
    """

    def __init__(
        self,
        utterance: Utterance,
        assistant: "Assistant",
        match: re.Match | None = None,
        command: Any = None,
    ) -> None:
        self.utterance = utterance
        self.assistant = assistant
        self.match = match
        self.command = command

    # -- raccourcis pratiques -------------------------------------------------
    @property
    def raw(self) -> str:
        return self.utterance.raw

    @property
    def norm(self) -> str:
        return self.utterance.norm

    @property
    def tokens(self) -> list[str]:
        return self.utterance.tokens

    @property
    def source(self) -> str:
        return self.utterance.source

    @property
    def config(self):
        """
        Configuration courante. Si aucun assistant n est fourni (tests
        unitaires du routeur), on retombe sur la configuration par defaut :
        les guards se comportent alors exactement comme en production.
        """
        config = getattr(self.assistant, "config", None)
        if config is not None:
            return config
        return _fallback_config()

    @property
    def storage(self):
        return self.assistant.storage

    @property
    def io(self):
        return self.assistant.io

    def group(self, index: int | str = 1) -> str:
        """
        Retourne le groupe capture, extrait de la chaine ORIGINALE (accents et
        casse preserves) grace a l'alignement raw/norm.
        """
        if self.match is None:
            return ""
        try:
            start, end = self.match.span(index)
        except (IndexError, error_types()):
            return ""
        if start < 0:
            return ""
        return self.raw[start:end].strip(" \t'\"-,.;:!?")

    @property
    def arg(self) -> str:
        """Premier groupe capture (cas le plus courant)."""
        return self.group(1)

    # -- interactions ---------------------------------------------------------
    def say(self, text: str) -> None:
        """Message intermediaire (avant la reponse finale)."""
        self.assistant.emit(text)

    def confirm(self, question: str) -> bool:
        """Demande une confirmation explicite (actions destructrices)."""
        return self.assistant.confirm(question)


def error_types():  # pragma: no cover - petite aide pour le except ci-dessus
    return re.error


_FALLBACK_CONFIG = None


def _fallback_config():
    """Configuration par defaut mise en cache, pour les contextes sans assistant."""
    global _FALLBACK_CONFIG
    if _FALLBACK_CONFIG is None:
        from config import load_config

        _FALLBACK_CONFIG = load_config()
    return _FALLBACK_CONFIG
