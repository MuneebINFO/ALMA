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


# Les DEUX voies vers l edition complete. Elles ne se ressemblent pas et le
# provider doit les distinguer : l une envoie la cle de l utilisateur droit a
# Anthropic, l autre envoie un jeton d abonne au relais.
VOIE_CLE = "cle"
VOIE_ABONNEMENT = "abonnement"

# L interrogation du Store passe par WinRT : une cinquantaine de millisecondes,
# a chaque phrase non reconnue. On garde donc la reponse quelques secondes --
# assez pour ne pas la payer a chaque mot, assez peu pour qu un achat qui
# vient d aboutir soit pris en compte tout de suite.
_DUREE_CACHE = 30.0
_cache_abonnement = {"quand": 0.0, "actif": False}


def _abonne_au_store(config) -> bool:
    """L abonnement du Store est-il actif ? Reponse gardee quelques secondes."""
    import time

    from core import abonnement_store

    if time.monotonic() - _cache_abonnement["quand"] < _DUREE_CACHE:
        return _cache_abonnement["actif"]
    identifiant = str((config.get("abonnement.store_id", "") if config else "") or "")
    actif = abonnement_store.abonne(identifiant)
    _cache_abonnement.update(quand=time.monotonic(), actif=actif)
    return actif


def oublier_le_cache() -> None:
    """A appeler apres un achat : la reponse gardee n est plus la bonne."""
    _cache_abonnement.update(quand=0.0, actif=False)


def voie(config) -> str:
    """
    Par ou passe l edition complete : « cle », « abonnement », ou rien.

    La CLE D ABORD. Quelqu un qui en a pose une l a fait exprès, et elle ne
    coute rien a personne d autre ; la consulter est par ailleurs instantane,
    la ou le Store demande un aller-retour WinRT.
    """
    if souhaitee(config) == COMPLETE and cle(config):
        return VOIE_CLE
    if _abonne_au_store(config):
        return VOIE_ABONNEMENT
    return ""


def active(config) -> str:
    """
    L edition qui s applique reellement.

    « complete » sans cle NI abonnement vaut « libre » : c est ce qui garantit
    qu Alma ne tente jamais un appel qu elle ne peut pas faire, et qu elle le
    dit au lieu d echouer.
    """
    return COMPLETE if voie(config) else LIBRE


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


# Regarder une image n est pas repondre a une question : il faut le dire
# autrement, sinon Alma repondrait « je ne reponds pas aux questions » a
# quelqu un qui n en a pose aucune.
SANS_REGARD_FR = ("Je sais prendre la photo, mais pas la regarder. "
                  "Il faudrait l'édition complète pour ça.")
SANS_REGARD_EN = ("I can take the photo, but not look at it. "
                  "That would need the complete edition.")


def sans_regard(langue: str = "fr") -> str:
    """La phrase dite quand on demande a Alma libre d analyser une image."""
    return SANS_REGARD_EN if langue == "en" else SANS_REGARD_FR
