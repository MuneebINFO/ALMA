"""Fixtures partagees par les tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Permet d importer le projet sans installation.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config  # noqa: E402
from core.registry import load_commands  # noqa: E402
from core.router import Router  # noqa: E402


class FakeIO:
    """Sortie de test : memorise tout au lieu d afficher, et repond aux questions."""

    source = "text"

    def __init__(self, answers=None):
        self.written = []
        self.answers = list(answers or [])

    def read(self, prompt: str = "") -> str:
        return self.answers.pop(0) if self.answers else "quitte"

    def write(self, text: str) -> None:
        self.written.append(text)

    def ask(self, question: str) -> str:
        self.written.append(question)
        return self.answers.pop(0) if self.answers else "non"

    def close(self) -> None:
        pass


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def router(config):
    load_commands()
    return Router()


@pytest.fixture
def assistant(tmp_path, config):
    """
    Assistant isole : donnees dans un dossier temporaire, pas de synthese
    vocale, pas de saisie clavier.
    """
    from core.assistant import Assistant

    test_config = load_config()
    test_config.set("paths.notes", str(tmp_path / "notes.json"))
    test_config.set("paths.reminders", str(tmp_path / "reminders.json"))
    test_config.set("paths.history", str(tmp_path / "history.json"))

    class SilentTTS:
        """Double de test : meme interface que TextToSpeech, sans moteur reel."""

        available = False
        voices: list = []
        error = ""

        def say(self, text, blocking=False):
            pass

        def wait(self, timeout=None):
            pass

        def list_voices(self):
            return []

        def shutdown(self):
            pass

    return Assistant(config=test_config, io=FakeIO(), tts=SilentTTS())
