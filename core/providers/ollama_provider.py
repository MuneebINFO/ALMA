"""
OllamaProvider : un modele de langage qui tourne SUR LA MACHINE.

Le projet s interdit toute IA generative payante. Ollama ne l est pas : c est
un serveur local, sans compte ni cle, qui charge un modele depuis le disque et
n ouvre aucune connexion vers l exterieur. Rien de ce qui est dit ne sort de
l ordinateur -- c est la meme promesse que le reste d Alma.

Ce qu il apporte : quand aucune regle ne correspond, Alma repond aujourd hui
« Je n ai pas compris » et s arrete la. Le modele prend alors le relais pour
REPONDRE A LA QUESTION -- une explication, une definition, une reformulation.
Il n execute rien : aucune commande, aucun fichier, aucun clic. Le corps
d Alma reste le moteur de regles ; le modele ne fait que parler.

Desactive par defaut, comme tout ce point d extension. Pour l activer :

    ai_fallback:
      enabled: true
      provider: ollama
      ollama:
        modele: qwen2.5:3b        # doit avoir ete telecharge (ollama pull)

Prerequis : Ollama installe et lance (https://ollama.com). Sans lui, le
provider le dit clairement au lieu d echouer en silence.
"""

from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)

HOTE_PAR_DEFAUT = "http://localhost:11434"
MODELE_PAR_DEFAUT = "qwen2.5:3b"
DELAI_PAR_DEFAUT = 30
LONGUEUR_MAX = 400          # une reponse lue a voix haute doit rester courte

# Le modele parle, il n agit pas. On le lui dit, sinon il propose d ouvrir des
# applications ou d appuyer sur des touches -- des promesses qu il ne peut
# pas tenir, et qu Alma ne relaiera pas.
CONSIGNE = (
    "Tu es la voix d'un assistant local nommé {nom}. Réponds en français, "
    "en deux phrases au maximum, sans formatage ni liste. "
    "Tu ne peux RIEN faire sur l'ordinateur : tu réponds seulement à la "
    "question posée. Si elle demande une action, dis simplement que tu ne "
    "sais pas la faire."
)


class OllamaProvider:
    """Provider qui interroge un modele de langage local, via Ollama."""

    name = "ollama"

    def __init__(self, config) -> None:
        self.config = config
        lire = config.get if config is not None else (lambda cle, defaut=None: defaut)
        self.hote = str(lire("ai_fallback.ollama.hote", HOTE_PAR_DEFAUT)
                        or HOTE_PAR_DEFAUT).rstrip("/")
        self.modele = str(lire("ai_fallback.ollama.modele", MODELE_PAR_DEFAUT)
                          or MODELE_PAR_DEFAUT)
        self.delai = int(lire("ai_fallback.ollama.timeout_seconds", DELAI_PAR_DEFAUT)
                         or DELAI_PAR_DEFAUT)
        self.nom_assistant = str(lire("general.assistant_name", "Alma") or "Alma")

    # -- verifications prealables --------------------------------------------
    def modeles_disponibles(self) -> list:
        """Les modeles presents sur la machine, ou [] si le serveur est absent."""
        import requests

        try:
            reponse = requests.get(self.hote + "/api/tags", timeout=3)
            reponse.raise_for_status()
            return [str(m.get("name", "")) for m in reponse.json().get("models", [])]
        except Exception as exc:
            log.debug("Ollama injoignable : %s", exc)
            return []

    def diagnostic(self) -> str:
        """Ce qui manque pour que le provider fonctionne. Vide si tout va bien."""
        modeles = self.modeles_disponibles()
        if not modeles:
            return ("Ollama ne répond pas sur " + self.hote
                    + ". Installez-le depuis ollama.com, puis lancez-le.")
        # « qwen2.5:3b » et « qwen2.5:3b-instruct » designent la meme famille :
        # on accepte le prefixe pour ne pas exiger le nom exact au caractere pres.
        if not any(m == self.modele or m.startswith(self.modele) for m in modeles):
            return ("Le modèle « " + self.modele + " » n'est pas téléchargé. "
                    "Lancez : ollama pull " + self.modele)
        return ""

    # -- interface du provider ------------------------------------------------
    def generate(self, query: str) -> str:
        import requests

        manque = self.diagnostic()
        if manque:
            return manque

        charge = {
            "model": self.modele,
            "prompt": query,
            "system": CONSIGNE.format(nom=self.nom_assistant),
            "stream": False,
            # Une reponse parlee n a pas besoin d etre longue, et chaque mot
            # produit coute du temps de calcul sur la machine.
            "options": {"num_predict": 160, "temperature": 0.3},
        }
        try:
            reponse = requests.post(self.hote + "/api/generate",
                                    json=charge, timeout=self.delai)
            reponse.raise_for_status()
            texte = str(reponse.json().get("response", "")).strip()
        except requests.Timeout:
            return ("Le modèle local n'a pas répondu en " + str(self.delai)
                    + " secondes. Essayez un modèle plus petit.")
        except json.JSONDecodeError:
            return "Ollama a renvoyé une réponse illisible."
        except Exception as exc:
            log.debug("Echec Ollama : %s", exc)
            return "Le modèle local n'a pas pu répondre (" + type(exc).__name__ + ")."

        return _raccourcir(texte) or "Le modèle local n'a rien répondu."


def _raccourcir(texte: str) -> str:
    """
    Ramene la reponse a ce qui s ecoute.

    Un modele deborde volontiers, meme quand on lui demande d etre bref. On
    coupe a la fin d une phrase plutot qu au milieu d un mot.
    """
    texte = " ".join((texte or "").split())
    if len(texte) <= LONGUEUR_MAX:
        return texte
    coupe = texte[:LONGUEUR_MAX]
    for ponctuation in (". ", "! ", "? "):
        position = coupe.rfind(ponctuation)
        if position > LONGUEUR_MAX // 2:
            return coupe[:position + 1].strip()
    return coupe.rsplit(" ", 1)[0].strip() + "…"
