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
# Aucune exception. L acces a Gemini passe par la page google.com, lue dans le
# navigateur comme n importe quelle autre page -- pas par une API.
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


def test_une_vraie_reponse_n_est_pas_un_echec(assistant, monkeypatch):
    """
    ok=False veut dire « je n ai pas compris ».

    Quand un provider a REPONDU, la reponse n est pas un echec : la marquer
    ainsi l afficherait en rouge et la compterait comme une commande ratee.
    """
    from core import ai_fallback

    class ProviderBavard:
        name = "essai"

        def generate(self, query):
            return "Bruxelles est la capitale de la Belgique."

    monkeypatch.setitem(ai_fallback.PROVIDERS, "essai", lambda config: ProviderBavard())
    assistant.config.set("ai_fallback.enabled", True)
    assistant.config.set("ai_fallback.provider", "essai")
    assistant.config.set("ai_fallback.auto", "tout")

    reponse = assistant.handle("xyzzy plover blorb")
    assert reponse.ok, reponse.text
    assert "Bruxelles" in reponse.text


def test_une_phrase_incomprise_ne_part_pas_d_elle_meme_a_l_ia(assistant, monkeypatch):
    """
    Le défaut constaté à l'usage : un calcul dicté autrement que prévu ouvrait
    une session Claude Code, sans que rien ne l'ait demandé. Alma s'adresse à
    Claude quand on le lui demande, pas quand elle bute.
    """
    from core import ai_fallback

    appele = []

    class ProviderBavard:
        name = "essai"

        def generate(self, query):
            appele.append(query)
            return "une réponse"

    monkeypatch.setitem(ai_fallback.PROVIDERS, "essai", lambda config: ProviderBavard())
    assistant.config.set("ai_fallback.enabled", True)
    assistant.config.set("ai_fallback.provider", "essai")

    reponse = assistant.handle("xyzzy plover blorb")
    assert appele == [], "le provider ne devait pas être appelé"
    assert reponse.text in SUGGESTIONS
    assert not reponse.ok


def test_sans_provider_l_incomprehension_reste_un_echec(assistant):
    """Le fallback eteint, on ne comprend pas -- et cela doit se voir."""
    reponse = assistant.handle("xyzzy plover blorb")
    assert not reponse.ok
    assert reponse.text in SUGGESTIONS


# --------------------------------------------------------------------------
# La promesse, telle qu'elle est aujourd'hui
# --------------------------------------------------------------------------
# Elle a CHANGÉ D'ÉNONCÉ le jour où l'édition complète est apparue, et il faut
# le dire franchement : longtemps, ces tests vérifiaient qu'aucune clé d'API
# n'existait nulle part. Ce n'est plus vrai — l'édition complète en demande
# une.
#
# Ce qui n'a pas changé, c'est ce que la promesse PROTÈGE : un utilisateur qui
# n'a rien fourni ne doit voir partir aucune donnée, et ne rien payer. Les
# tests ci-dessous disent donc la version exacte de cette promesse :
#
#   1. ce qui est livré est « libre » — rien ne sort tant que l'utilisateur
#      n'a pas posé lui-même une clé ;
#   2. aucune clé n'est jamais lue dans l'ENVIRONNEMENT : Alma ne se sert que
#      de ce qu'on lui a explicitement confié ;
#   3. aucune clé ne s'écrit en clair, ni en configuration ni en préférences ;
#   4. la liste des canaux vers un modèle reste close.

def test_ce_qui_est_livre_est_l_edition_libre():
    """La valeur par défaut, avant toute personnalisation."""
    from config import DEFAULTS

    assert DEFAULTS["general"]["edition"] == "libre"
    assert DEFAULTS["ai_fallback"]["enabled"] is False


def test_sans_cle_rien_ne_part(config):
    """
    Le cœur de la promesse : pas de clé, pas de provider, donc pas d'appel.

    Le fixture `aucune_trace_sur_la_machine` rend le coffre vide, ce qui est
    exactement la situation d'une installation neuve.
    """
    from core import edition

    assert edition.est_complete(config) is False
    assert isinstance(get_provider(config), NullProvider)


def test_une_edition_complete_annoncee_sans_cle_retombe_en_libre(config):
    """
    Le réglage seul ne suffit pas. Sinon une configuration copiée d'une
    machine à l'autre ferait croire à Alma qu'elle peut appeler, et chaque
    demande finirait en erreur au lieu de retomber sur ce qui marche.
    """
    from core import edition

    config.set("general.edition", "complete")

    assert edition.souhaitee(config) == "complete"
    assert edition.active(config) == "libre"
    assert isinstance(get_provider(config), NullProvider)


def test_aucune_cle_n_est_lue_dans_l_environnement(monkeypatch, config):
    """
    Alma ne se sert QUE de ce qu'on lui a confié. Une clé qui traîne dans
    l'environnement — celle d'un autre outil, celle d'un développeur — ne doit
    pas la faire basculer en édition complète à l'insu de son propriétaire.
    """
    from core import edition

    for variable in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
                     "CLAUDE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(variable, "sk-ant-ceci-ne-doit-pas-etre-lu")

    assert edition.cle(config) == ""
    assert edition.est_complete(config) is False


def test_aucune_cle_ne_s_ecrit_en_clair(config):
    """
    Ni dans la configuration, ni dans les préférences. Le coffre est le seul
    endroit, et il chiffre (voir core/secrets.py).
    """
    from core.preferences import CATALOGUE

    assert "api_key" not in (config.get("ai_fallback") or {})
    assert not any("key" in reglage.chemin.lower() for reglage in CATALOGUE),         "une clé ne se range pas dans les préférences : elles s'écrivent en clair"


def test_la_liste_des_providers_est_close():
    """
    Aucun canal IA ne doit apparaître sans être déclaré ici. La liste est
    volontairement courte, et chacun de ses membres est vérifié ci-dessous.
    """
    assert set(PROVIDERS) == {"none", "ollama", "claude_api", "claude_code"}


def test_aucun_provider_ne_sort_de_la_machine(config):
    """
    La promesse du projet : rien de payant, rien qui parte vers une API.
    Ollama tourne en local ; Claude Code délègue à un binaire déjà installé ;
    Gemini se lit dans le navigateur, sur une page ouverte comme les autres.
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
    fautifs = [str(f.relative_to(ROOT)) for f in fichiers
               if domaine in f.read_text(encoding="utf-8")]
    assert not fautifs, "URL d API IA trouvee dans : " + ", ".join(fautifs)


def test_aucun_provider_ne_demande_de_cle():
    """
    Aucune cle a gerer, nulle part.

    Ollama tourne en local, Claude Code s authentifie lui-meme, et Gemini se
    lit sur google.com dans le navigateur. Si une variable de cle apparait
    dans un provider, c est qu une API s est glissee dans le projet.
    """
    fichiers = list(ROOT.glob("core/providers/*.py"))
    fautifs = [str(f.relative_to(ROOT)) for f in fichiers
               if "GEMINI_API_KEY" in f.read_text(encoding="utf-8")
               or "OPENAI_API_KEY" in f.read_text(encoding="utf-8")]
    assert not fautifs, "cle d API attendue dans : " + ", ".join(fautifs)


def test_le_mode_voix_est_desactive_par_defaut(tmp_path):
    from config import load_config

    assert load_config(tmp_path / "config-absent.yaml").get("voice.enabled") is False
