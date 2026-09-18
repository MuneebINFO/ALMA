"""
L abonnement vendu par le Microsoft Store.

C est Windows qui encaisse. « S abonner » ouvre SA fenetre d achat, contre la
carte deja enregistree sur le compte Microsoft : un clic, et c est fini. Ni
cle a coller, ni mot de passe, ni compte a creer -- le compte Microsoft fait
l identite, et Microsoft gere les renouvellements, les remboursements et la
TVA de chaque pays.

TROIS CHOSES QU IL FAUT SAVOIR AVANT DE TOUCHER A CE FICHIER.

Une application Win32 doit RATTACHER le contexte du Store a une fenetre
(IInitializeWithWindow) avant tout achat. Sans cela l appel leve, parce que
Windows ne sait pas devant quelle fenetre afficher sa boite de dialogue. Alma
est une application Win32 empaquetee (Desktop Bridge), pas une appli UWP :
cette etape n est donc jamais facultative ici.

Rien de tout cela ne fonctionne HORS du Store. Lance depuis les sources, ou
installe a la main, le Store n a pas de licence a montrer et toutes ces
fonctions rendent « pas abonne ». C est le comportement voulu : on retombe en
edition libre, qui marche sans rien, au lieu de refuser de demarrer. C est
aussi pourquoi rien ici ne leve jamais.

Et la licence lue localement NE SUFFIT PAS a ouvrir le relais. Un client
modifie peut affirmer ce qu il veut ; c est `jeton()` qui rend une preuve
signee par Microsoft, que le relais fait valider par Microsoft lui-meme. La
licence locale ne sert qu a l affichage -- savoir quoi montrer dans l onglet.
"""

from __future__ import annotations

import logging

from core import winrt_utils

log = logging.getLogger(__name__)


def _contexte(fenetre: int = 0):
    """Le contexte du Store, rattache a une fenetre si on en fournit une."""
    from winsdk.windows.services.store import StoreContext

    contexte = StoreContext.get_default()
    if fenetre:
        # Obligatoire pour une appli Win32 : sans cela, request_purchase_async
        # leve au lieu d afficher la boite de dialogue d achat.
        from winsdk._winrt import initialize_with_window

        initialize_with_window(contexte, fenetre)
    return contexte


def disponible() -> bool:
    """Le Store est-il joignable depuis cette installation ?"""
    try:
        _contexte()
        return True
    except Exception as exc:
        log.debug("Store indisponible : %s", exc)
        return False


# --------------------------------------------------------------------------
# Lire l abonnement
# --------------------------------------------------------------------------
async def _licences_async():
    licence = await _contexte().get_app_license_async()
    return licence.add_on_licenses


def abonne(store_id: str) -> bool:
    """
    Cet add-on est-il actif pour l utilisateur courant ?

    Pour l AFFICHAGE seulement. Ne jamais s en servir pour autoriser un appel
    facturable : cette reponse vient de la machine de l utilisateur, et le
    relais exige une preuve signee (voir `jeton`).
    """
    if not store_id:
        return False
    try:
        licences = winrt_utils.executer(_licences_async())
    except Exception as exc:
        log.debug("Licences illisibles : %s", exc)
        return False

    for cle in licences:
        licence = licences[cle]
        if getattr(licence, "sku_store_id", "").startswith(store_id) \
                and licence.is_active:
            return True
    return False


# --------------------------------------------------------------------------
# Prouver l abonnement au relais
# --------------------------------------------------------------------------
async def _jeton_async(audience: str):
    return await _contexte().get_customer_collections_id_async(audience, "")


def jeton(audience: str = "") -> str:
    """
    La preuve, signee par Microsoft, que cet utilisateur est bien abonne.

    C est ce que le relais envoie a Microsoft pour verification avant de
    laisser passer une requete -- et c est la seule chose qui compte, parce
    qu elle ne peut pas etre fabriquee par un client modifie.
    """
    try:
        return winrt_utils.executer(_jeton_async(audience)) or ""
    except Exception as exc:
        log.debug("Jeton d'abonnement indisponible : %s", exc)
        return ""


# --------------------------------------------------------------------------
# Acheter
# --------------------------------------------------------------------------
async def _acheter_async(store_id: str, fenetre: int):
    return await _contexte(fenetre).request_purchase_async(store_id)


# Ce que l achat a donne, et ce qu on en dit. Les libelles sont bilingues
# parce qu ils s affichent (regle 2).
RESULTATS = {
    "SUCCEEDED": (True, "C'est fait, merci.", "All set, thank you."),
    "ALREADY_PURCHASED": (True, "Vous êtes déjà abonné.",
                          "You're already subscribed."),
    "NOT_PURCHASED": (False, "L'achat a été annulé.", "The purchase was cancelled."),
    "NETWORK_ERROR": (False, "Le Store n'est pas joignable.",
                      "The Store can't be reached."),
    "SERVER_ERROR": (False, "Le Store a rencontré un problème.",
                     "The Store ran into a problem."),
}


def acheter(store_id: str, fenetre: int) -> tuple:
    """
    Ouvre la fenetre d achat de Windows. Rend (reussi, message_fr, message_en).

    `fenetre` est le handle de la fenetre d Alma : Windows en a besoin pour
    savoir devant quoi s afficher, et l achat echoue sans lui.
    """
    if not store_id:
        return False, "Aucun abonnement n'est configuré.", "No subscription is configured."
    try:
        resultat = winrt_utils.executer(_acheter_async(store_id, fenetre))
    except Exception as exc:
        log.warning("Achat impossible : %s", exc)
        return (False,
                "Impossible d'ouvrir la fenêtre d'achat : " + str(exc),
                "Couldn't open the purchase window: " + str(exc))

    from winsdk.windows.services.store import StorePurchaseStatus

    for nom, (reussi, fr, en) in RESULTATS.items():
        if resultat.status == getattr(StorePurchaseStatus, nom):
            return reussi, fr, en
    # Un statut que Windows aurait ajoute depuis : on ne pretend pas savoir.
    return (False, "L'achat n'a pas abouti.", "The purchase didn't go through.")
