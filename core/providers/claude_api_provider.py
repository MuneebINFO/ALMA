"""
ClaudeApiProvider : le cerveau de l edition complete.

C est le SEUL endroit du projet qui appelle une API facturable, et il ne
s allume que lorsque l utilisateur a pose sa propre cle (voir core/edition.py
et core/secrets.py). En edition libre, ce module n est meme pas importe.

CE QU IL FAIT, ET CE QU IL NE FAIT PAS. Il repond, et il regarde des images.
Il n execute rien : ouvrir une application, monter le son, changer d onglet
restent l affaire du routeur, qui le fait en dix millisecondes et sans un
centime. On ne vient ici que lorsqu il n y a personne d autre pour repondre.

UNE REPONSE EST LUE A VOIX HAUTE, et c est la contrainte qui gouverne tout
le reste. Trois phrases s ecoutent ; un paragraphe ne s ecoute pas. Pas de
listes, pas de titres, pas de gras -- « **deux** » se prononcerait
« asterisque asterisque deux ». La consigne systeme le dit, et
`text_utils.sans_balisage` rattrape ce qui passe quand meme.

LA LANGUE SUIT LA DEMANDE, comme partout ailleurs dans Alma (regle 2). Elle
n est pas devinee par le modele : elle lui est donnee, parce que
`detect_language` a deja tranche en amont et que les deux doivent dire la
meme chose.

Rien de ce module n ecrit la cle dans un journal, pas meme tronquee.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Opus 5 par defaut : c est le modele le plus capable, et la qualite des
# reponses est ce que l edition complete vend. Sonnet 5 repond a peu pres
# deux fois plus vite pour moitie moins cher -- un reglage, pas une fatalite :
#   ai_fallback:
#     claude_api:
#       modele: claude-sonnet-5
MODELE_PAR_DEFAUT = "claude-opus-5"

# Une reponse parlee est courte ; ce plafond n est pas une cible, c est une
# securite contre une reponse qui partirait en longueur.
JETONS_MAX = 1024

# Un assistant vocal est le cas d usage que la documentation range parmi ceux
# ou la profondeur de reflexion ne se paie pas : on attend une reponse, pas
# une dissertation. « low » coupe la latence et le cout sans rien changer a
# la justesse sur ce genre de question.
EFFORT = "low"

DELAI_PAR_DEFAUT = 30

CONSIGNE = """Tu es la voix de {nom}, un assistant qui tourne sur l'ordinateur \
de l'utilisateur.

Ta réponse va être LUE À VOIX HAUTE par une synthèse vocale. Cela commande \
tout le reste :
- trois phrases au maximum, souvent une seule suffit ;
- aucun formatage : ni liste, ni titre, ni gras, ni tiret en début de ligne ;
- des nombres écrits comme on les dit.

Réponds en {langue}.

Tu ne peux rien faire sur l'ordinateur toi-même — {nom} s'en charge avec ses \
propres commandes. Si on te demande une action, dis simplement que tu ne sais \
pas la faire. Si tu ignores quelque chose, dis-le franchement : une réponse \
inventée est pire qu'un aveu."""

LANGUES = {"fr": "français", "en": "English"}


class ClaudeApiProvider:
    """Provider qui interroge l API Claude avec la cle de l utilisateur."""

    name = "claude_api"

    def __init__(self, config) -> None:
        self.config = config
        lire = config.get if config is not None else (lambda cle, defaut=None: defaut)
        self.modele = str(lire("ai_fallback.claude_api.modele", MODELE_PAR_DEFAUT)
                          or MODELE_PAR_DEFAUT)
        self.delai = int(lire("ai_fallback.claude_api.timeout_seconds", DELAI_PAR_DEFAUT)
                         or DELAI_PAR_DEFAUT)
        self.nom = str(lire("general.assistant_name", "ALMA") or "ALMA")
        self._client = None

    # -- le client -----------------------------------------------------------
    def client(self):
        """
        Le client SDK, construit une seule fois.

        La cle est lue du coffre a CHAQUE construction plutot que retenue au
        demarrage : l utilisateur peut la retirer en cours de route, et Alma
        doit alors cesser d appeler, pas continuer avec une copie en memoire.
        """
        if self._client is not None:
            return self._client
        from core import edition

        cle = edition.cle(self.config)
        if not cle:
            raise RuntimeError("aucune clé d'API : l'édition complète est inactive")
        import anthropic

        self._client = anthropic.Anthropic(api_key=cle, timeout=float(self.delai))
        return self._client

    def diagnostic(self) -> str:
        """Ce qui manque pour que ce provider fonctionne, ou une chaine vide."""
        from core import edition

        if not edition.cle(self.config):
            return "aucune clé d'API n'est enregistrée"
        try:
            import anthropic                  # noqa: F401
        except ImportError:
            return "le paquet « anthropic » n'est pas installé"
        return ""

    # -- parler --------------------------------------------------------------
    def generate(self, query: str, langue: str = "fr") -> str:
        """Repond a la question, en deux ou trois phrases."""
        return self._demander(
            [{"role": "user", "content": query}], langue)

    # -- regarder ------------------------------------------------------------
    def analyser_image(self, image: bytes, question: str, langue: str = "fr") -> str:
        """
        Decrit ce qu il y a sur l image, en repondant a `question`.

        L image part telle qu elle sort de la camera -- entiere, sans
        recadrage. Un modele de vision retrouve tres bien une main dans un
        cadre : detourer avant d envoyer aurait coute une dependance de cent
        quatre-vingts megaoctets pour economiser une fraction de centime.
        """
        if not image:
            raise ValueError("image vide")
        import base64

        return self._demander([{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(image).decode("ascii"),
                }},
                {"type": "text", "text": question},
            ],
        }], langue)

    # -- le fond commun ------------------------------------------------------
    def _demander(self, messages, langue: str) -> str:
        consigne = CONSIGNE.format(nom=self.nom,
                                   langue=LANGUES.get(langue, LANGUES["fr"]))
        reponse = self.client().messages.create(
            model=self.modele,
            max_tokens=JETONS_MAX,
            system=consigne,
            output_config={"effort": EFFORT},
            messages=messages,
        )

        # Un refus de securite arrive en HTTP 200, avec du contenu vide : sans
        # ce test, l utilisateur recevrait le silence pour toute reponse.
        if reponse.stop_reason == "refusal":
            return ("Je préfère ne pas répondre à ça." if langue != "en"
                    else "I'd rather not answer that.")

        morceaux = [bloc.text for bloc in reponse.content if bloc.type == "text"]
        return "\n".join(morceaux).strip()
