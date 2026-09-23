"""
Les deux editions d Alma, et la frontiere entre elles.

    libre     -- de l AUTOMATISATION. Les commandes declarees, la memoire du
                 contexte, les sources locales : Wikipedia, les calculs, la
                 meteo, l heure. Rien ne part vers un modele, rien n est
                 facturable, il n y a rien a fournir.

    complete  -- « ALMA+ ». Tout cela, plus un modele lorsque la demande
                 depasse ce qui est declare : une question ouverte, une image
                 a regarder. S obtient par ABONNEMENT, et par lui seul.

UNE SEULE VOIE, ET C EST VOULU. Il a existe un second chemin : coller sa
propre cle d API. Il a ete retire entierement -- pas masque, retire -- parce
qu un produit qui propose « abonnez-vous, ou bien procurez-vous une cle chez
un tiers » demande a l utilisateur de choisir entre deux choses qu il ne sait
pas comparer, et en fait fuir la plupart. L abonnement passe par le Store :
un clic, la carte deja enregistree, rien a comprendre.

Il ne reste donc RIEN dans ce projet qui lise ou range une cle d API. Des
tests le verifient.

LA FRONTIERE N EST PAS « simple contre complique ». Elle est : existe-t-il
une source locale ou deterministe ? Si oui, c est gratuit et ca le reste --
un resume Wikipedia et un calcul RESSEMBLENT a de la reflexion, mais ils ne
coutent rien et fonctionnent hors ligne. Les faire passer au payant rendrait
l edition libre moins bonne qu avant, ce qu on ne fait pas.

Et l ordre ne s inverse jamais : meme abonne, une demande que les commandes
savent traiter est traitee PAR ELLES. Le routeur repond en moins de dix
millisecondes et sans un centime ; on ne va chercher un modele que lorsqu il
n y a personne d autre pour repondre.

DEUX ETATS, PAS UN. Ce que la configuration ANNONCE (`souhaitee`) et ce qui
s applique VRAIMENT (`active`) different des que l abonnement n est pas -- ou
plus -- actif. On retombe alors en edition libre, qui marche sans rien,
plutot que de promettre ce qu on ne peut pas tenir.
"""

from __future__ import annotations

LIBRE = "libre"
COMPLETE = "complete"
EDITIONS = (LIBRE, COMPLETE)

# Le nom commercial. L identifiant interne reste « complete » -- il est ecrit
# dans les preferences, et le changer casserait les installations existantes
# pour un libelle.
NOM_COMPLETE_FR = "ALMA+"
NOM_COMPLETE_EN = "ALMA+"
NOM_LIBRE_FR = "ALMA"
NOM_LIBRE_EN = "ALMA"

# L interrogation du Store passe par WinRT : une cinquantaine de millisecondes,
# a chaque phrase non reconnue. On garde donc la reponse quelques secondes --
# assez pour ne pas la payer a chaque mot, assez peu pour qu un achat qui
# vient d aboutir soit pris en compte tout de suite.
_DUREE_CACHE = 30.0
_cache_abonnement = {"quand": 0.0, "actif": False}


def souhaitee(config) -> str:
    """L edition ANNONCEE par la configuration, sans verifier qu elle tient."""
    if config is None:
        return LIBRE
    valeur = str(config.get("general.edition", LIBRE) or LIBRE).strip().lower()
    return valeur if valeur in EDITIONS else LIBRE


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


def abonne(config) -> bool:
    """L abonnement est-il actif ? C est la seule porte vers ALMA+."""
    return _abonne_au_store(config)


def active(config) -> str:
    """
    L edition qui s applique reellement.

    Sans abonnement actif, c est « libre » -- meme si la configuration
    pretend le contraire. C est ce qui garantit qu Alma ne tente jamais un
    appel qu elle ne peut pas faire, et qu elle le dit au lieu d echouer.
    """
    return COMPLETE if abonne(config) else LIBRE


def est_complete(config) -> bool:
    """Alma a-t-elle le droit ET les moyens d aller chercher un modele ?"""
    return active(config) == COMPLETE


def nom(edition_: str, langue: str = "fr") -> str:
    """Le nom commercial d une edition, dans la langue demandee."""
    if edition_ == COMPLETE:
        return NOM_COMPLETE_EN if langue == "en" else NOM_COMPLETE_FR
    return NOM_LIBRE_EN if langue == "en" else NOM_LIBRE_FR


# --------------------------------------------------------------------------
# Ce qu on dit a qui demande plus que l automatisation
# --------------------------------------------------------------------------
# Factuel, pas commercial. L utilisateur d Alma libre n a rien de casse : il
# a un outil d automatisation qui fait ce pour quoi il est fait, et qui le
# lui dit franchement plutot que d echouer en silence.
HORS_PORTEE_FR = ("Je ne réponds pas aux questions : je fais de l'automatisation. "
                  "ALMA+, elle, sait le faire.")
HORS_PORTEE_EN = ("I don't answer questions — I automate things. "
                  "ALMA+ does answer them.")


def hors_portee(langue: str = "fr") -> str:
    """La phrase dite quand la demande releve de l abonnement."""
    return HORS_PORTEE_EN if langue == "en" else HORS_PORTEE_FR


# Regarder une image n est pas repondre a une question : il faut le dire
# autrement, sinon Alma repondrait « je ne reponds pas aux questions » a
# quelqu un qui n en a pose aucune.
SANS_REGARD_FR = ("Je sais prendre la photo, mais pas la regarder. "
                  "Il faudrait ALMA+ pour ça.")
SANS_REGARD_EN = ("I can take the photo, but not look at it. "
                  "That would need ALMA+.")


def sans_regard(langue: str = "fr") -> str:
    """La phrase dite quand on demande a Alma libre d analyser une image."""
    return SANS_REGARD_EN if langue == "en" else SANS_REGARD_FR
