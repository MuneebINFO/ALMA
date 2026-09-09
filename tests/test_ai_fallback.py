"""
Garanties sur le fallback IA.

Ces tests verrouillent la promesse du projet : par defaut, Alma ne contacte
AUCUNE IA, ne lance AUCUN sous-processus et ne coute rien. Le seul canal IA
possible, une fois active, est le CLI Claude Code.
"""

import copy
import subprocess
from pathlib import Path

import pytest

from config import Config
from core.ai_fallback import PROVIDERS, SUGGESTIONS, NullProvider, get_provider, handle_with_ai
from core.providers.claude_code_provider import ClaudeCodeProvider

ROOT = Path(__file__).resolve().parent.parent

# Domaines d IA appelables directement : ils ne doivent apparaitre nulle part.
# Tout doit passer par le CLI Claude Code, jamais par une API en direct.
DOMAINES_INTERDITS = [
    "api.openai.com",
    "api.anthropic.com",
    "generativelanguage.googleapis.com",
    "api.groq.com",
    "api.mistral.ai",
]


def config_avec(config, **surcharges):
    """Copie de la configuration avec la section ai_fallback modifiee."""
    donnees = copy.deepcopy(config.data)
    donnees["ai_fallback"].update(surcharges)
    return Config(donnees)


# --------------------------------------------------------------------------
# Etat par defaut : aucun appel exterieur
# --------------------------------------------------------------------------
def test_le_fallback_est_desactive_par_defaut(tmp_path):
    """
    Ce que recoit une machine neuve, sans config.yaml.

    On repart d un fichier absent plutot que de la configuration courante :
    la machine de developpement a le droit d avoir active la delegation chez
    elle, cela ne doit rien changer a ce qui est LIVRE.
    """
    from config import load_config

    neuve = load_config(tmp_path / "config-absent.yaml")
    assert neuve.get("ai_fallback.enabled") is False
    assert isinstance(get_provider(neuve), NullProvider)
    assert isinstance(get_provider(None), NullProvider)


def test_desactive_le_fallback_repond_sans_jamais_appeler_claude(config, monkeypatch):
    """
    Le test central demande par le cahier des charges : avec enabled=false,
    on obtient "commande non reconnue" SANS jamais tenter de lancer `claude`.
    """
    def interdit(*args, **kwargs):
        raise AssertionError("aucun sous-processus ne doit etre lance quand enabled=false")

    monkeypatch.setattr(subprocess, "run", interdit)
    monkeypatch.setattr(subprocess, "Popen", interdit)

    reponse = handle_with_ai("ecris-moi un script python", config)
    assert reponse in SUGGESTIONS
    # Reponses volontairement courtes : pas de renvoi vers l aide.
    assert len(reponse) < 40
    assert "aide" not in reponse.lower()


def test_desactive_aucun_appel_reseau(config, monkeypatch):
    """Meme garantie cote reseau : rien ne sort de la machine."""
    import requests

    def interdit(*args, **kwargs):
        raise AssertionError("appel reseau interdit dans le fallback par defaut")

    monkeypatch.setattr(requests, "get", interdit)
    monkeypatch.setattr(requests, "post", interdit)
    assert handle_with_ai("une demande totalement inconnue", config) in SUGGESTIONS


def test_commande_inconnue_de_bout_en_bout_ne_lance_rien(assistant, monkeypatch):
    """Meme garantie en passant par l assistant complet."""
    def interdit(*args, **kwargs):
        raise AssertionError("aucun sous-processus ne doit etre lance")

    monkeypatch.setattr(subprocess, "run", interdit)
    reponse = assistant.handle("xyzzy plover blorb")
    assert not reponse.ok
    assert reponse.text in SUGGESTIONS


def test_aucune_cle_api_dans_la_configuration(config):
    """Alma ne gere aucune cle : Claude Code s authentifie lui-meme."""
    assert "api_key" not in (config.get("ai_fallback") or {})


def test_la_liste_des_providers_est_close():
    """
    Aucun canal IA ne doit apparaître sans être déclaré ici. La liste est
    volontairement courte, et chacun de ses membres est vérifié ci-dessous.
    """
    assert set(PROVIDERS) == {"none", "ollama", "claude_code"}


def test_aucun_provider_ne_sort_de_la_machine(config):
    """
    La promesse du projet : rien de payant, rien qui parte vers une API.
    Ollama tourne en local ; Claude Code délègue à un binaire déjà installé.
    """
    from core.providers.ollama_provider import OllamaProvider

    hote = OllamaProvider(config).hote
    assert hote.startswith("http://localhost") or "127.0.0.1" in hote


def test_le_modele_local_ne_peut_rien_executer(config):
    """
    Le cerveau reste le moteur de règles : le modèle ne fait que répondre.
    Sa consigne le lui dit, faute de quoi il promettrait des actions.
    """
    from core.providers.ollama_provider import CONSIGNE

    consigne = CONSIGNE.lower()
    assert "rien" in consigne and "ordinateur" in consigne


@pytest.mark.parametrize("domaine", DOMAINES_INTERDITS)
def test_aucun_appel_direct_a_une_api_ia_dans_le_code(domaine):
    """Balayage du code source : aucune URL d API IA ne doit y figurer."""
    fichiers = (
        list(ROOT.glob("*.py"))
        + list(ROOT.glob("core/*.py"))
        + list(ROOT.glob("core/providers/*.py"))
        + list(ROOT.glob("commands/*.py"))
    )
    fautifs = [str(f.relative_to(ROOT)) for f in fichiers if domaine in f.read_text(encoding="utf-8")]
    assert not fautifs, "URL d API IA trouvee dans : " + ", ".join(fautifs)


def test_le_mode_voix_est_desactive_par_defaut(tmp_path):
    from config import load_config

    assert load_config(tmp_path / "config-absent.yaml").get("voice.enabled") is False
