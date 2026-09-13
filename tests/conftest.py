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


@pytest.fixture(autouse=True)
def aucune_trace_sur_la_machine(monkeypatch):
    """
    Aucun test ne doit LAISSER quoi que ce soit derriere lui.

    Une suite qui exerce l'assistant de bout en bout execute VRAIMENT les
    commandes : « search Google for gift ideas » ouvrait un onglet, « copy X
    to the clipboard » ecrasait le presse-papiers, « take a screenshot »
    remplissait un dossier -- a chaque lancement, sur la machine de qui
    lance les tests, pendant qu'il travaille.

    On coupe donc les sorties a la racine, pour TOUS les tests. Ce qui est
    verifie -- le routage, la reponse, la langue -- n'en depend pas ; un test
    qui a besoin de la vraie fonction la remplace lui-meme.
    """
    from commands import websites
    from core import win_utils

    monkeypatch.setattr(websites, "open_url", lambda *a, **k: True)
    monkeypatch.setattr(win_utils, "set_clipboard", lambda *a, **k: True)
    monkeypatch.setattr(win_utils, "launch", lambda *a, **k: (False, "test"))
    monkeypatch.setattr(win_utils, "take_screenshot",
                        lambda *a, **k: (True, "capture_de_test.png"))


@pytest.fixture(autouse=True)
def application_claude_fermee(monkeypatch):
    """
    Par defaut, l application Claude est vue comme fermee.

    Sans cela le routage dependrait de ce qui tourne sur la machine : « demande
    a Claude ... » irait a l application ici, et au navigateur ailleurs. Les
    tests qui veulent l application ouverte la rouvrent eux-memes.
    """
    monkeypatch.setattr("core.claude_app.fenetre", lambda: None)


def config_de_test(path=None):
    """
    La configuration, fallback IA coupe.

    La machine de developpement a le droit d activer la delegation a Claude
    Code dans son config.yaml. Les tests, eux, ne doivent lancer aucun
    sous-processus : ils repartent donc toujours d un fallback eteint. Les
    tests qui veulent l inverse le rallument eux-memes.
    """
    config = load_config(path) if path else load_config()
    config.set("ai_fallback.enabled", False)
    return config


@pytest.fixture(scope="session")
def config():
    return config_de_test()


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

    test_config = config_de_test()
    test_config.set("paths.notes", str(tmp_path / "notes.json"))
    test_config.set("paths.reminders", str(tmp_path / "reminders.json"))
    test_config.set("paths.history", str(tmp_path / "history.json"))
    test_config.set("paths.memory", str(tmp_path / "souvenirs.json"))
    # Les personnalisations aussi : un test qui renomme l'assistant ne doit
    # pas renommer celui de la personne qui lance la suite.
    test_config.set("paths.preferences", str(tmp_path / "preferences.json"))

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


@pytest.fixture(scope="session")
def tk_root():
    """
    Une UNIQUE racine Tk, invisible, pour toute la session de test.

    Tcl supporte mal qu'on crée puis détruise plusieurs interpréteurs dans le
    même processus : deux modules qui faisaient chacun leur `tk.Tk()`
    finissaient par « Can't find a usable tk.tcl ». Une seule racine partagée,
    jamais détruite avant la fin, contourne le problème.
    """
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:                       # pas d'affichage disponible
        pytest.skip("Tk indisponible : " + str(exc))
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass
