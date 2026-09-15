"""
Les deux editions d Alma, et la frontiere entre elles.

    libre     -- de l AUTOMATISATION. Les commandes declarees, la memoire du
                 contexte, les sources locales : Wikipedia, les calculs, la
                 meteo, l heure. Rien ne part vers un modele, rien n est
                 facturable, il n y a aucune cle a fournir.

    complete  -- tout cela, plus un AGENT lorsque la demande depasse ce qui
                 est declare : une question ouverte, une image a regarder.
                 Suppose une cle d API fournie par l utilisateur.

LA FRONTIERE N EST PAS « simple contre complique ». Elle est : existe-t-il
une source locale ou deterministe ? Si oui, c est gratuit et ca le reste --
un resume Wikipedia et un calcul RESSEMBLENT a de la reflexion, mais ils ne
coutent rien et fonctionnent hors ligne. Les faire passer au payant rendrait
l edition libre moins bonne qu avant, ce qu on ne fait pas.

Et l ordre ne s inverse jamais : meme en edition complete, une demande que
les commandes savent traiter est traitee PAR ELLES. Le routeur repond en
moins de dix millisecondes et sans un centime ; on ne va chercher un modele
que lorsqu il n y a personne d autre pour repondre.

DEUX ETATS, PAS UN. Ce que l utilisateur a CHOISI (`souhaitee`) et ce qui
s applique VRAIMENT (`active`) different des que la cle manque ou n est plus
lisible -- coffre pose sous un autre compte Windows, fichier abime. On
retombe alors en edition libre, qui marche sans rien, plutot que de promettre
ce qu on ne peut pas tenir.
"""

from __future__ import annotations

from core import secrets

LIBRE = "libre"
COMPLETE = "complete"
EDITIONS = (LIBRE, COMPLETE)

# Le nom sous lequel la cle est rangee dans le coffre.
CLE_API = "anthropic_api_key"


def souhaitee(config) -> str:
    """L edition CHOISIE, telle quelle -- sans verifier qu elle est tenable."""
    if config is None:
        return LIBRE
    valeur = str(config.get("general.edition", LIBRE) or LIBRE).strip().lower()
    return valeur if valeur in EDITIONS else LIBRE


def cle(config) -> str:
    """La cle d API en clair, ou une chaine vide. Ne leve jamais."""
    return secrets.lire(CLE_API, config)


def active(config) -> str:
    """
    L edition qui s applique reellement.

    « complete » sans cle lisible vaut « libre » : c est ce qui garantit
    qu Alma ne tente jamais un appel qu elle ne peut pas faire, et qu elle le
    dit au lieu d echouer.
    """
    if souhaitee(config) != COMPLETE:
        return LIBRE
    return COMPLETE if cle(config) else LIBRE


def est_complete(config) -> bool:
    """Alma a-t-elle le droit ET les moyens d aller chercher un modele ?"""
    return active(config) == COMPLETE


def poser_cle(config, valeur: str) -> bool:
    """
    Range la cle dans le coffre. Rend True si elle est ecrite.

    Ne touche PAS a `general.edition` : c est une preference, elle passe donc
    par `assistant.personnaliser` comme toutes les autres (regle 3), chez
    l appelant qui a un assistant sous la main. Ici on ne fait que le coffre.
    """
    valeur = (valeur or "").strip()
    if not valeur:
        return False
    return secrets.poser(CLE_API, valeur, config)


def retirer_cle(config) -> bool:
    """Oublie la cle. L edition redevient « libre » d elle-meme, faute de cle."""
    return secrets.oublier(CLE_API, config)


# --------------------------------------------------------------------------
# Ce qu on dit a qui demande plus que l automatisation
# --------------------------------------------------------------------------
# Factuel, pas commercial. L utilisateur d Alma libre n a rien de casse : il
# a un outil d automatisation qui fait ce pour quoi il est fait, et qui le
# lui dit franchement plutot que d echouer en silence.
HORS_PORTEE_FR = ("Je ne réponds pas aux questions : je fais de l'automatisation. "
                  "L'édition complète, elle, sait le faire.")
HORS_PORTEE_EN = ("I don't answer questions — I automate things. "
                  "The complete edition does answer them.")


def hors_portee(langue: str = "fr") -> str:
    """La phrase dite quand la demande releve de l edition complete."""
    return HORS_PORTEE_EN if langue == "en" else HORS_PORTEE_FR
