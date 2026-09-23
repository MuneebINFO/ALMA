"""
Ce que Windows autorise : micro et camera.

POURQUOI CE MODULE EXISTE. La certification du Store a renvoye « Unusable
Feature: Voice commands », testee sur une machine neuve avec une connexion
etablie. Rien n etait casse : Windows refusait simplement le micro a une
application empaquetee, et PortAudio rend alors du SILENCE -- pas une erreur.

Alma attendait donc indefiniment une voix qui ne pouvait pas arriver.
L orbe tournait, le vu-metre restait a zero, rien ne signalait quoi que ce
soit. Du point de vue de qui teste, la fonction principale ne marche pas et
l application n en dit rien.

C est exactement la regle 6 -- le silence doit se distinguer d une panne --
appliquee au cas ou personne n avait pense : le silence venu d une case a
cocher dans les reglages de Windows.

CE QU IL FAIT. Il demande a Windows l etat reel de l autorisation, et le
traduit en une phrase qui dit quoi faire. Windows sait repondre precisement :
refuse par l utilisateur, coupe pour toutes les applications, jamais demande.
Chacun appelle un geste different, et les confondre ferait chercher au mauvais
endroit.

HORS PAQUET, rien de tout cela ne s applique : une application Win32 lancee
depuis les sources n est soumise a aucune de ces autorisations. On repond
alors « autorise », parce que c est vrai -- et parce qu un developpement
bloque par une verification qui ne le concerne pas serait absurde.
"""

from __future__ import annotations

import logging

from core import winrt_utils

log = logging.getLogger(__name__)

MICRO = "microphone"
CAMERA = "webcam"

# Les etats rendus par ce module. « inconnu » n est pas un echec : c est le
# cas normal hors paquet, et il ne doit jamais empecher Alma de demarrer.
AUTORISE = "autorise"
REFUSE_UTILISATEUR = "refuse_utilisateur"
REFUSE_SYSTEME = "refuse_systeme"
NON_DECLARE = "non_declare"
A_DEMANDER = "a_demander"
INCONNU = "inconnu"

# Les pages de reglages de Windows, par capacite. Y emmener l utilisateur
# vaut mieux que lui decrire un chemin a suivre dans six menus.
REGLAGES = {
    MICRO: "ms-settings:privacy-microphone",
    CAMERA: "ms-settings:privacy-webcam",
}

# Ce qu on dit, et ce qu il y a a faire. Bilingue (regle 2), et chaque phrase
# nomme le geste : « autorisez Alma » n est pas « rallumez le micro pour
# toutes les applications ».
_EXPLICATIONS = {
    (MICRO, REFUSE_UTILISATEUR): (
        "Windows bloque le micro pour ALMA. Autorisez-la dans les paramètres "
        "de confidentialité.",
        "Windows is blocking the microphone for ALMA. Allow it in your privacy "
        "settings."),
    (MICRO, REFUSE_SYSTEME): (
        "L'accès au micro est coupé pour toutes les applications de cet "
        "ordinateur.",
        "Microphone access is turned off for every app on this computer."),
    (MICRO, NON_DECLARE): (
        "ALMA n'a pas déclaré le micro : cette installation est incomplète.",
        "ALMA didn't declare the microphone: this install is incomplete."),
    (CAMERA, REFUSE_UTILISATEUR): (
        "Windows bloque la caméra pour ALMA. Autorisez-la dans les paramètres "
        "de confidentialité.",
        "Windows is blocking the camera for ALMA. Allow it in your privacy "
        "settings."),
    (CAMERA, REFUSE_SYSTEME): (
        "L'accès à la caméra est coupé pour toutes les applications de cet "
        "ordinateur.",
        "Camera access is turned off for every app on this computer."),
    (CAMERA, NON_DECLARE): (
        "ALMA n'a pas déclaré la caméra : cette installation est incomplète.",
        "ALMA didn't declare the camera: this install is incomplete."),
}


def _traduire(statut) -> str:
    from winsdk.windows.security.authorization.appcapabilityaccess import (
        AppCapabilityAccessStatus)

    table = {
        AppCapabilityAccessStatus.ALLOWED: AUTORISE,
        AppCapabilityAccessStatus.DENIED_BY_USER: REFUSE_UTILISATEUR,
        AppCapabilityAccessStatus.DENIED_BY_SYSTEM: REFUSE_SYSTEME,
        AppCapabilityAccessStatus.NOT_DECLARED_BY_APP: NON_DECLARE,
        AppCapabilityAccessStatus.USER_PROMPT_REQUIRED: A_DEMANDER,
    }
    return table.get(statut, INCONNU)


def etat(capacite: str) -> str:
    """
    Ou en est l autorisation pour cette capacite.

    Ne leve jamais. Hors paquet, ou si l API n est pas joignable, rend
    « inconnu » -- et l appelant continue comme si de rien n etait, ce qui
    est le bon comportement : ces autorisations ne s appliquent alors pas.
    """
    try:
        from winsdk.windows.security.authorization.appcapabilityaccess import (
            AppCapability)

        return _traduire(AppCapability.create(capacite).check_access())
    except Exception as exc:
        log.debug("Autorisation %s illisible : %s", capacite, exc)
        return INCONNU


def utilisable(capacite: str) -> bool:
    """
    Peut-on s en servir ?

    « inconnu » compte comme oui, et « a demander » aussi : dans les deux cas
    on laisse l essai avoir lieu plutot que de bloquer sur une supposition.
    Seul un refus FRANC de Windows arrete quelque chose.
    """
    return etat(capacite) not in (REFUSE_UTILISATEUR, REFUSE_SYSTEME, NON_DECLARE)


def explication(capacite: str, langue: str = "fr") -> str:
    """
    Pourquoi ça ne marche pas, et quoi faire. Chaine vide si tout va bien.

    C est cette phrase qui manquait : sans elle, un micro refuse par Windows
    et un micro qui n entend rien se ressemblent exactement.
    """
    phrases = _EXPLICATIONS.get((capacite, etat(capacite)))
    if not phrases:
        return ""
    return phrases[1] if langue == "en" else phrases[0]


async def _demander_async(capacite: str):
    from winsdk.windows.security.authorization.appcapabilityaccess import (
        AppCapability)

    return await AppCapability.create(capacite).request_access_async()


def demander(capacite: str) -> str:
    """
    Demande l autorisation a Windows, qui affiche sa propre invite.

    A n appeler que sur « a demander » : sur un refus deja exprime, Windows
    ne reaffiche rien, et insister ne ferait que donner l illusion d agir.
    """
    try:
        return _traduire(winrt_utils.executer(_demander_async(capacite)))
    except Exception as exc:
        log.debug("Demande d'autorisation %s impossible : %s", capacite, exc)
        return INCONNU


def ouvrir_les_reglages(capacite: str) -> bool:
    """Emmene l utilisateur sur la bonne page des reglages de Windows."""
    adresse = REGLAGES.get(capacite)
    if not adresse:
        return False
    from core.win_utils import launch

    ok, _detail = launch(adresse)
    return ok
