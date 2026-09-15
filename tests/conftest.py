"""Fixtures partagees par les tests."""

from __future__ import annotations

import copy
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
    from core import desktop, media_control, win_utils

    def rien(*a, **k):
        return None

    def vrai(*a, **k):
        return True

    # -- ce qui SORT : navigateur, presse-papiers, fichiers, processus -------
    monkeypatch.setattr(websites, "open_url", vrai)
    monkeypatch.setattr(win_utils, "set_clipboard", vrai)
    # Le presse-papiers se LIT aussi : « lis le presse-papiers » renvoyait ce
    # que la personne venait de copier, et un test sur la langue de la reponse
    # echouait selon le contenu. Regle 5 : rien qui depende de la machine.
    monkeypatch.setattr(win_utils, "get_clipboard", lambda *a, **k: "presse papiers de test")
    monkeypatch.setattr(win_utils, "launch", lambda *a, **k: (False, "test"))
    monkeypatch.setattr(win_utils, "take_screenshot",
                        lambda *a, **k: (True, "capture_de_test.png"))
    monkeypatch.setattr(win_utils, "open_folder", lambda chemin: (False, str(chemin)))
    monkeypatch.setattr(win_utils, "kill_process", lambda *a, **k: (False, "test"))
    monkeypatch.setattr(win_utils, "run_command", lambda *a, **k: (False, "test"))
    monkeypatch.setattr(win_utils, "lock_workstation", lambda *a, **k: False)

    # -- le CLAVIER et la SOURIS : la suite ne tape rien, ne clique rien -----
    # « copie », « nouvel onglet », « ferme la fenetre » envoient de vraies
    # touches a la fenetre au premier plan -- celle ou la personne travaille.
    monkeypatch.setattr(win_utils, "press_key", vrai)
    monkeypatch.setattr(win_utils, "press_combo", vrai)
    monkeypatch.setattr(win_utils, "raccourci", vrai)
    monkeypatch.setattr(win_utils, "type_text", vrai)

    # -- le SON et l ECRAN ---------------------------------------------------
    # Sans cela la suite montait le son, le coupait, changeait la luminosite
    # et mettait en pause ce qui jouait -- a chaque lancement.
    monkeypatch.setattr(win_utils, "get_volume", lambda *a, **k: 50)
    monkeypatch.setattr(win_utils, "set_volume", vrai)
    monkeypatch.setattr(win_utils, "change_volume", lambda delta: max(0, min(100, 50 + delta)))
    monkeypatch.setattr(win_utils, "set_mute", vrai)
    monkeypatch.setattr(win_utils, "is_muted", lambda *a, **k: False)
    monkeypatch.setattr(win_utils, "get_brightness", lambda *a, **k: 50)
    monkeypatch.setattr(win_utils, "set_brightness", vrai)
    monkeypatch.setattr(win_utils, "beep", rien)
    monkeypatch.setattr(win_utils, "notify", rien)
    # Les bruitages aussi : ils partent en asynchrone, donc sans ralentir la
    # suite -- mais ils se jouent bel et bien sur les haut-parleurs de qui la
    # lance. Un test qui veut verifier qu'un bruitage a eu lieu repose sa
    # propre doublure par-dessus.
    from core.sons import Bruitages

    monkeypatch.setattr(Bruitages, "jouer", lambda self, nom: False)

    # -- le COFFRE ----------------------------------------------------------
    # Le garde-fou le plus important de ce fichier. `secrets.lire` ouvre le
    # VRAI coffre de qui lance la suite : si sa cle d API s y trouve, Alma
    # bascule en edition complete au milieu des tests et se met a passer de
    # vrais appels FACTURES, sur des phrases de test.
    #
    # Coffre vide par defaut, donc, et ecriture neutralisee. Un test qui veut
    # l edition complete pose sa propre doublure par-dessus -- et celui-la ne
    # doit toujours appeler aucun reseau : c est le provider qu il remplace.
    from core import secrets

    monkeypatch.setattr(secrets, "lire", lambda nom, config=None: "")
    monkeypatch.setattr(secrets, "poser", lambda nom, valeur, config=None: True)
    monkeypatch.setattr(secrets, "oublier", lambda nom, config=None: True)

    # -- la CAMERA ----------------------------------------------------------
    # Regle 4 ET regle 5 a la fois. `capturer` allume vraiment la camera : un
    # temoin qui s illumine pendant que la suite tourne, et une photo ecrite
    # dans les Images de qui la lance. Et `disponible`, appele par le guard,
    # interroge le materiel : la commande se routerait ici et pas sur une
    # machine sans webcam.
    #
    # On pose donc UNE camera, toujours la meme, qui rend toujours la meme
    # image. Un test qui veut l absence de camera la retire lui-meme.
    from core import camera

    monkeypatch.setattr(camera, "lister", lambda: [("id-test", "Camera de test")])
    monkeypatch.setattr(camera, "capturer",
                        lambda identifiant="": b"jpeg-de-test")
    monkeypatch.setattr(camera, "enregistrer",
                        lambda image, dossier: (True, str(dossier) + "/photo-de-test.jpg"))

    # -- les LECTEURS et les FENETRES ---------------------------------------
    monkeypatch.setattr(media_control, "_agir_sur_session", vrai)
    monkeypatch.setattr(desktop, "mettre_au_premier_plan", vrai)
    monkeypatch.setattr(desktop, "fermer_fenetre", vrai)
    monkeypatch.setattr(desktop, "deplacer_vers_ecran", vrai)
    monkeypatch.setattr(desktop, "naviguer_dans_fenetre", vrai)

    # -- les ECRANS : deux, toujours les memes ------------------------------
    # Regle 5. Une dizaine de tests supposaient un second moniteur et
    # tombaient des qu il etait debranche -- on les prenait alors pour des
    # « echecs de la machine », ce qui masquait les vrais. Un test qui veut
    # une autre configuration la pose lui-meme, par-dessus.
    monkeypatch.setattr(desktop, "ecrans", lambda: [
        desktop.Ecran(1, (0, 0, 1920, 1080), 1),
        desktop.Ecran(2, (1920, 0, 3840, 1080), 2),
    ])
    # La langue de repli est un etat de module, regle par l'assistant. Sans
    # cette remise a zero, un test qui passe Alma en anglais changerait la
    # langue des suivants, selon l'ordre d'execution.
    from core import text_utils

    monkeypatch.setattr(text_utils, "LANGUE_PAR_DEFAUT", "fr")


@pytest.fixture(autouse=True)
def application_claude_fermee(monkeypatch):
    """
    Par defaut, l application Claude est vue comme fermee.

    Sans cela le routage dependrait de ce qui tourne sur la machine : « demande
    a Claude ... » irait a l application ici, et au navigateur ailleurs. Les
    tests qui veulent l application ouverte la rouvrent eux-memes.
    """
    monkeypatch.setattr("core.claude_app.fenetre", lambda: None)


# Un chemin de preferences qui n existe pas : c est ainsi qu on obtient la
# configuration D ORIGINE, sans ce que l utilisateur de la machine a
# personnalise. Sans cela, un poste ou Alma s appelle Jarvis et connait le
# prenom de son proprietaire ferait echouer des tests qui n ont rien a voir.
SANS_PREFERENCES = Path(__file__).resolve().parent / "aucune_preference.json"


def config_de_test(path=None):
    """
    La configuration d origine, fallback IA coupe.

    Deux choses dont les tests ne doivent pas dependre : la machine de
    developpement a le droit d activer la delegation a Claude Code dans son
    config.yaml -- les tests, eux, ne lancent aucun sous-processus -- et son
    proprietaire a le droit d avoir personnalise Alma. On repart donc d un
    fallback eteint et d aucune preference. Les tests qui veulent l inverse
    les remettent eux-memes.
    """
    config = load_config(path, preferences_file=SANS_PREFERENCES)
    config.set("ai_fallback.enabled", False)
    return config


@pytest.fixture(scope="session")
def config():
    """
    Construite UNE fois : la relire a chaque test couterait plusieurs secondes
    sur la suite entiere. `config_rendue_intacte` la remet d aplomb ensuite.
    """
    return config_de_test()


@pytest.fixture(autouse=True)
def config_rendue_intacte(config):
    """
    La configuration partagee est rendue a son etat d origine apres CHAQUE test.

    Elle est partagee pour la vitesse -- et c etait un piege. Un test qui
    ecrivait « ai_fallback.enabled: true » le laissait derriere lui, et les
    tests d Ollama, qui verifient justement qu aucun appel ne part quand c est
    eteint, tombaient ou non selon l ORDRE d execution. Un echec qui
    n apparait qu en suite complete, et pas en isolant le test, est le plus
    couteux de tous a comprendre.

    Elle ne peut pas simplement devenir propre a chaque test : `router` est de
    portee session et en depend. D ou cet instantane, pris sur `data` seul --
    c est tout l etat mutable.
    """
    avant = copy.deepcopy(config.data)
    try:
        yield
    finally:
        config.data = avant


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
