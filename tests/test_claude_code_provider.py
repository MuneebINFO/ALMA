"""
Tests du ClaudeCodeProvider.

Aucun test ne lance le vrai CLI Claude Code : subprocess.run est remplace par
un espion qui enregistre les arguments recus.
"""

import copy
import subprocess

import pytest

from config import Config
from core.ai_fallback import get_provider
from core.providers.claude_code_provider import ClaudeCodeProvider


@pytest.fixture
def config_active(config, tmp_path):
    """Configuration avec le fallback active et un dossier de travail valide."""
    donnees = copy.deepcopy(config.data)
    donnees["ai_fallback"]["enabled"] = True
    donnees["ai_fallback"]["provider"] = "claude_code"
    donnees["ai_fallback"]["claude_code"]["working_dir"] = str(tmp_path)
    return Config(donnees)


class RunEspion:
    """Remplace subprocess.run et memorise l appel."""

    def __init__(self, stdout="reponse de Claude Code", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.appels = []

    def __call__(self, argv, **kwargs):
        self.appels.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


@pytest.fixture
def claude_present(monkeypatch):
    """Simule un CLI `claude` installe."""
    monkeypatch.setattr(
        "core.providers.claude_code_provider.shutil.which",
        lambda name: "C:/faux/chemin/claude.exe",
    )


def test_le_provider_est_choisi_quand_le_fallback_est_active(config_active):
    assert isinstance(get_provider(config_active), ClaudeCodeProvider)


def test_appel_headless_avec_les_bons_arguments(config_active, claude_present, monkeypatch, tmp_path):
    espion = RunEspion()
    monkeypatch.setattr(subprocess, "run", espion)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    reponse = ClaudeCodeProvider(config_active).generate("resume-moi ce dossier")

    assert reponse == "reponse de Claude Code"
    argv, kwargs = espion.appels[0]
    assert argv == [
        "C:/faux/chemin/claude.exe",
        "-p",
        "resume-moi ce dossier",
        "--output-format",
        "text",
    ]
    # Le dossier de travail borne l action de Claude Code.
    assert kwargs["cwd"] == str(tmp_path)
    assert kwargs["timeout"] == 120
    # Jamais de shell : la requete dictee ne peut pas etre injectee.
    assert kwargs.get("shell") in (None, False)


def test_aucun_drapeau_de_permission_nest_ajoute(config_active, claude_present, monkeypatch):
    """Les permissions restent celles de Claude Code, Alma n en invente pas."""
    espion = RunEspion()
    monkeypatch.setattr(subprocess, "run", espion)
    ClaudeCodeProvider(config_active).generate("bonjour")
    argv = " ".join(espion.appels[0][0])
    for drapeau in ("--allowedTools", "--dangerously-skip-permissions", "--permission-mode"):
        assert drapeau not in argv


def test_working_dir_obligatoire(config, claude_present, monkeypatch):
    """Sans dossier de travail explicite, aucun sous-processus n est lance."""
    def interdit(*args, **kwargs):
        raise AssertionError("aucun appel ne doit partir sans working_dir")

    monkeypatch.setattr(subprocess, "run", interdit)
    donnees = copy.deepcopy(config.data)
    donnees["ai_fallback"]["enabled"] = True
    reponse = ClaudeCodeProvider(Config(donnees)).generate("fais quelque chose")
    assert "working_dir" in reponse


def test_cli_absent_signale_clairement(config_active, monkeypatch):
    monkeypatch.setattr("core.providers.claude_code_provider.shutil.which", lambda name: None)
    reponse = ClaudeCodeProvider(config_active).generate("bonjour")
    assert "introuvable" in reponse.lower()


def test_cle_api_detectee_declenche_un_avertissement(config_active, claude_present, monkeypatch):
    """Une cle API ferait facturer l API au lieu du quota d abonnement."""
    monkeypatch.setattr(subprocess, "run", RunEspion())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    provider = ClaudeCodeProvider(config_active)
    assert provider.api_key_detected() is True
    reponse = provider.generate("bonjour")
    assert "ANTHROPIC_API_KEY" in reponse
    assert "abonnement" in reponse.lower()


def test_le_provider_ne_modifie_jamais_la_variable_denvironnement(
    config_active, claude_present, monkeypatch
):
    monkeypatch.setattr(subprocess, "run", RunEspion())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    ClaudeCodeProvider(config_active).generate("bonjour")
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-test"


def test_timeout_gere_proprement(config_active, claude_present, monkeypatch):
    def expire(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 120)

    monkeypatch.setattr(subprocess, "run", expire)
    reponse = ClaudeCodeProvider(config_active).generate("tache tres longue")
    assert "delai" in reponse.lower()
    assert "timeout_seconds" in reponse


def test_erreur_du_cli_gere_proprement(config_active, claude_present, monkeypatch):
    monkeypatch.setattr(subprocess, "run", RunEspion(stdout="", returncode=1, stderr="panne"))
    reponse = ClaudeCodeProvider(config_active).generate("bonjour")
    assert "erreur" in reponse.lower() and "panne" in reponse


def test_timeout_configurable(config, tmp_path, claude_present, monkeypatch):
    espion = RunEspion()
    monkeypatch.setattr(subprocess, "run", espion)
    donnees = copy.deepcopy(config.data)
    donnees["ai_fallback"]["enabled"] = True
    donnees["ai_fallback"]["claude_code"]["working_dir"] = str(tmp_path)
    donnees["ai_fallback"]["claude_code"]["timeout_seconds"] = 300
    ClaudeCodeProvider(Config(donnees)).generate("bonjour")
    assert espion.appels[0][1]["timeout"] == 300
