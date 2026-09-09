"""
GeminiProvider : poser la question a Google Gemini, en arriere-plan.

Rien ne s ouvre a l ecran. Pas de navigateur, pas d onglet, pas de fenetre :
Alma interroge l API, recoit du texte, et le dit comme si elle repondait
elle-meme. C est voulu -- l utilisateur pose une question a son assistant, pas
a un site.

Ce que ce module NE fait pas, et ne doit jamais faire :

  - il ne DETIENT aucune cle. La cle vient de l environnement
    (GEMINI_API_KEY), il se contente de constater sa presence ou son absence,
    et ne l ecrit ni ne la modifie jamais -- meme discipline que pour
    ANTHROPIC_API_KEY dans le provider Claude Code ;
  - il n execute RIEN sur la machine. Il repond, un point c est tout. Le corps
    d Alma reste le moteur de regles : c est lui qui agit.

La cle gratuite s obtient sur Google AI Studio. Sans elle, le provider le dit
clairement au lieu d echouer en silence.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

# Ce module est le SEUL du projet autorise a nommer une API d IA en direct.
# Un test le verifie, et refuse toute autre apparition ailleurs.
HOTE = "https://generativelanguage.googleapis.com"
MODELE_PAR_DEFAUT = "gemini-2.5-flash"
DELAI_PAR_DEFAUT = 20

VARIABLE_CLE = "GEMINI_API_KEY"
# Google publie ses outils sous deux noms selon les epoques : on accepte les
# deux plutot que d obliger a redefinir une variable deja posee.
VARIABLES_ACCEPTEES = (VARIABLE_CLE, "GOOGLE_API_KEY")

# Ce qu on demande au modele. Il repond a la place d Alma, donc il doit parler
# comme elle : court, en francais, sans mise en forme -- ce sera lu a voix
# haute, et « **gras** » se dirait « asterisque asterisque ».
CONSIGNE = (
    "Tu réponds à la place d'un assistant vocal francophone. Réponds en "
    "français, en une à trois phrases, en texte simple : pas de listes, pas "
    "de gras, pas de titres, aucun signe de mise en forme. Va droit au fait, "
    "sans formule d'introduction ni proposition d'aide supplémentaire. Si tu "
    "ne sais pas, dis-le simplement."
)

ABSENCE_DE_CLE = (
    "Aucune clé Gemini n'est configurée sur cette machine. Créez-en une "
    "gratuitement sur Google AI Studio, puis placez-la dans la variable "
    + VARIABLE_CLE + " (ou dans un fichier .env à la racine du projet). "
    "Alma la lit, ne la modifie jamais et ne la conserve nulle part."
)


class GeminiProvider:
    """Provider qui pose la question a Gemini et rend sa reponse."""

    name = "gemini"

    def __init__(self, config) -> None:
        self.config = config
        lire = config.get if config else (lambda cle, defaut=None: defaut)
        self.modele = str(lire("ai_fallback.gemini.modele", MODELE_PAR_DEFAUT)
                          or MODELE_PAR_DEFAUT)
        self.delai = int(lire("ai_fallback.gemini.timeout_seconds", DELAI_PAR_DEFAUT)
                         or DELAI_PAR_DEFAUT)

    # -- verifications prealables --------------------------------------------
    def cle(self) -> str:
        """
        La cle d API, lue dans l environnement. Jamais ecrite, jamais stockee.

        Elle ne passe pas par config.yaml a dessein : ce fichier se copie, se
        partage et se pousse par megarde.
        """
        for variable in VARIABLES_ACCEPTEES:
            valeur = os.environ.get(variable, "").strip()
            if valeur:
                return valeur
        return ""

    def diagnostic(self) -> str:
        """Ce qui empeche de fonctionner, ou une chaine vide si tout est pret."""
        if not self.cle():
            return ABSENCE_DE_CLE
        try:
            import requests  # noqa: F401
        except ImportError:
            return "La librairie « requests » est absente : pip install requests."
        return ""

    # -- appel ---------------------------------------------------------------
    def generate(self, query: str) -> str:
        """
        Pose la question et rend la reponse. Ne leve jamais d exception.

        La cle voyage dans un en-tete, jamais dans l URL : une URL se retrouve
        dans les journaux, les historiques et les messages d erreur.
        """
        query = (query or "").strip()
        if not query:
            return "Je n'ai pas saisi la question."
        souci = self.diagnostic()
        if souci:
            return souci

        import requests

        url = (HOTE + "/v1beta/models/" + self.modele + ":generateContent")
        corps = {
            "systemInstruction": {"parts": [{"text": CONSIGNE}]},
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": 400},
        }
        try:
            reponse = requests.post(
                url,
                headers={"x-goog-api-key": self.cle(),
                         "Content-Type": "application/json"},
                data=json.dumps(corps),
                timeout=self.delai,
            )
        except Exception as exc:
            log.debug("Appel a Gemini impossible : %s", exc)
            return "Je n'ai pas réussi à joindre Gemini. Vérifiez la connexion."

        if reponse.status_code != 200:
            return _erreur_lisible(reponse, self.modele)
        return _texte_de(reponse) or "Gemini n'a rien répondu."


def _texte_de(reponse) -> str:
    """Le texte de la reponse, quelle que soit la forme du decoupage."""
    try:
        donnees = reponse.json()
    except Exception:
        return ""
    morceaux = []
    for candidat in donnees.get("candidates") or []:
        for part in (candidat.get("content") or {}).get("parts") or []:
            texte = part.get("text")
            if texte:
                morceaux.append(texte)
    return " ".join(" ".join(morceaux).split())


def _erreur_lisible(reponse, modele: str) -> str:
    """
    Une erreur HTTP traduite en phrase actionnable.

    Les deux cas frequents mis a part -- cle refusee, modele inconnu -- on
    rend le message de Google plutot qu un code : il dit souvent quoi faire.
    """
    try:
        detail = ((reponse.json().get("error") or {}).get("message") or "").strip()
    except Exception:
        detail = ""
    if reponse.status_code in (401, 403):
        return ("La clé Gemini a été refusée. Vérifiez " + VARIABLE_CLE
                + (" (" + detail + ")" if detail else "") + ".")
    if reponse.status_code == 404:
        return ("Le modèle « " + modele + " » est introuvable. Changez "
                "ai_fallback.gemini.modele dans config.yaml"
                + (" (" + detail + ")" if detail else "") + ".")
    if reponse.status_code == 429:
        return "Le quota Gemini est atteint pour le moment. Réessayez plus tard."
    return ("Gemini a renvoyé une erreur " + str(reponse.status_code)
            + (" : " + detail if detail else "") + ".")
