"""
ClaudeCodeProvider : delegation au CLI Claude Code installe sur la machine.

Principe : Alma ne "sait" rien de plus que Claude Code. Il se contente de
transmettre la requete non reconnue au binaire `claude` en mode headless
(`claude -p "requete" --output-format text`) et de renvoyer sa sortie.

Consequences importantes, volontaires :
  - Les capacites disponibles sont EXACTEMENT celles de Claude Code sur cette
    machine (raisonnement, lecture/ecriture de fichiers, execution de
    commandes, web si active). Ni plus, ni moins.
  - Les PERMISSIONS restent celles configurees pour Claude Code. Ce provider
    n ajoute deliberement aucun drapeau du type --allowedTools ou
    --dangerously-skip-permissions : Alma n invente pas sa propre liste
    d autorisations.
  - La facturation suit l abonnement Claude tant qu aucune variable
    ANTHROPIC_API_KEY n est definie. Le provider ne touche JAMAIS a cette
    variable ; il se contente de signaler sa presence pour eviter une
    facturation API surprise a la place du quota d abonnement.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_COMMAND = "claude"
DEFAULT_TIMEOUT = 120

# Le CLI ecrit en UTF-8, sur toutes les plateformes. Sans le dire, Python
# decode avec l encodage local -- cp1252 sous Windows -- et « le systeme a ete
# cree » revient en « le systÃ¨me a Ã©tÃ© crÃ©Ã© », qu Alma lirait tel quel.
ENCODAGE = "utf-8"

# Sous Windows, lancer un programme console depuis Alma -- qui tourne sans
# console -- en ouvre une, noire, au premier plan. Elle a fait croire que
# l assistant « ouvrait Claude » alors qu il ne faisait que l interroger.
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# L etat de connexion se lit en une seconde : assez court pour le diagnostic,
# assez long pour un disque lent.
SONDAGE_TIMEOUT = 20

AVERTISSEMENT_CONNEXION = (
    "Claude Code est installe mais pas connecte sur cette machine. Ouvrez un "
    "terminal et lancez « claude auth login » : la delegation fonctionnera "
    "ensuite sans rien changer d autre. Attention, la connexion de "
    "l application Claude ne vaut pas pour le CLI : ce sont deux comptes "
    "ouverts separement."
)

AVERTISSEMENT_CLE_API = (
    "ATTENTION : la variable ANTHROPIC_API_KEY est definie sur cette machine. "
    "Claude Code va donc facturer cet appel sur l API au lieu d utiliser le quota "
    "de votre abonnement. Supprimez cette variable si ce n est pas voulu."
)


class ClaudeCodeProvider:
    """Provider qui sous-traite la requete au CLI Claude Code."""

    name = "claude_code"

    def __init__(self, config) -> None:
        self.config = config
        self.command = str(
            config.get("ai_fallback.claude_code.command", DEFAULT_COMMAND) or DEFAULT_COMMAND
        )
        self.timeout = int(
            config.get("ai_fallback.claude_code.timeout_seconds", DEFAULT_TIMEOUT) or DEFAULT_TIMEOUT
        )
        self.working_dir = str(config.get("ai_fallback.claude_code.working_dir", "") or "")

    # -- verifications prealables --------------------------------------------
    def resolve_command(self) -> str:
        """Chemin complet du binaire `claude`, ou chaine vide s il est absent."""
        return shutil.which(self.command) or ""

    def resolve_working_dir(self) -> Path | None:
        """
        Dossier de travail borne. Volontairement SANS valeur par defaut :
        laisser Claude Code ecrire dans un dossier choisi au hasard serait
        dangereux, donc l utilisateur doit le declarer explicitement.
        """
        if not self.working_dir.strip():
            return None
        expanded = os.path.expandvars(os.path.expanduser(self.working_dir))
        return Path(expanded)

    def api_key_detected(self) -> bool:
        """True si une cle API est presente (donc facturation API, pas abonnement)."""
        return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())

    def connexion(self) -> tuple:
        """
        Etat de connexion du CLI, sans consommer de quota.

        `claude auth status` repond en JSON et n appelle pas le modele : c est
        la seule facon de savoir AVANT d essayer. Le compte de l application
        Claude et celui du CLI sont deux connexions distinctes -- l une peut
        etre ouverte et l autre non.

        Retourne (connecte, methode). `connecte` vaut None si la question n a
        pas pu etre posee.
        """
        binaire = self.resolve_command()
        if not binaire:
            return None, ""
        try:
            resultat = subprocess.run(
                [binaire, "auth", "status"],
                capture_output=True, encoding=ENCODAGE, errors="replace",
                stdin=subprocess.DEVNULL, timeout=SONDAGE_TIMEOUT,
                creationflags=SANS_FENETRE,
            )
            etat = json.loads((resultat.stdout or "").strip() or "{}")
        except Exception as exc:
            log.debug("Etat de connexion illisible : %s", exc)
            return None, ""
        return bool(etat.get("loggedIn")), str(etat.get("authMethod", "") or "")

    def check(self) -> list:
        """Liste des problemes bloquants, vide si tout est pret."""
        problemes = []
        if not self.resolve_command():
            problemes.append(
                "Le CLI Claude Code est introuvable (commande « " + self.command + " »). "
                "Verifiez qu il est installe et accessible dans le PATH."
            )
        working_dir = self.resolve_working_dir()
        if working_dir is None:
            problemes.append(
                "Aucun dossier de travail n est defini. Renseignez "
                "ai_fallback.claude_code.working_dir dans config.yaml pour borner "
                "le dossier dans lequel Claude Code a le droit d agir."
            )
        elif not working_dir.is_dir():
            problemes.append("Le dossier de travail « " + str(working_dir) + " » n existe pas.")
        return problemes

    # -- appel ---------------------------------------------------------------
    def generate(self, query: str) -> str:
        """
        Transmet la requete au CLI Claude Code et renvoie sa reponse.
        Ne leve jamais d exception : renvoie un message lisible en cas d echec.
        """
        query = (query or "").strip()
        if not query:
            return "Je n'ai rien recu a transmettre a Claude Code."

        problemes = self.check()
        if problemes:
            return "Delegation a Claude Code impossible. " + " ".join(problemes)

        binaire = self.resolve_command()
        working_dir = self.resolve_working_dir()

        prefixe = ""
        if self.api_key_detected():
            log.warning(AVERTISSEMENT_CLE_API)
            prefixe = AVERTISSEMENT_CLE_API + "\n\n"

        # La requete est passee comme ARGUMENT (jamais via un shell) : aucun
        # risque d injection de commande depuis ce que dicte l utilisateur.
        argv = [binaire, "-p", query, "--output-format", "text"]
        log.debug("Appel de Claude Code : %s (cwd=%s)", argv[:2], working_dir)

        try:
            resultat = subprocess.run(
                argv,
                cwd=str(working_dir),
                capture_output=True,
                encoding=ENCODAGE,
                errors="replace",
                stdin=subprocess.DEVNULL,
                timeout=self.timeout,
                creationflags=SANS_FENETRE,
            )
        except subprocess.TimeoutExpired:
            return (
                prefixe + "Claude Code n'a pas repondu dans le delai imparti ("
                + str(self.timeout) + " secondes). Augmentez "
                "ai_fallback.claude_code.timeout_seconds si la tache est longue."
            )
        except Exception as exc:
            log.exception("Echec de l appel a Claude Code")
            return prefixe + "L'appel a Claude Code a echoue : " + str(exc)

        sortie = (resultat.stdout or "").strip()
        if resultat.returncode != 0:
            # Le CLI n ecrit pas toujours ses erreurs sur stderr : « Not logged
            # in » part sur la sortie standard. On regarde donc les deux, sans
            # quoi on annoncerait une erreur sans dire laquelle.
            erreur = (resultat.stderr or "").strip() or sortie or "aucun detail"
            if "not logged in" in erreur.lower() or "/login" in erreur:
                return prefixe + AVERTISSEMENT_CONNEXION
            return prefixe + "Claude Code a renvoye une erreur : " + erreur
        if not sortie:
            return prefixe + "Claude Code n'a rien renvoye."
        return prefixe + sortie
