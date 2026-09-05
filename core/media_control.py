"""
Controle de la lecture, application par application.

Les touches multimedia globales de Windows ne visent qu une seule application
a la fois : si Chrome et Firefox jouent tous les deux, impossible de choisir.
On passe donc par les sessions media du systeme (GSMTC), qui exposent chaque
lecteur separement -- c est ce qui permet « mets pause sur l ecran 2 ».

Repli automatique quand un lecteur n expose pas de session (beaucoup de
lecteurs video de sites de streaming) : on met sa fenetre au premier plan et
on envoie la touche pause, comme le ferait un utilisateur.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core import desktop, win_utils

log = logging.getLogger(__name__)

# Etats renvoyes par Windows pour une session media.
EN_LECTURE = 4
EN_PAUSE = 5

VK_ESPACE = 0x20
VK_K = 0x4B


@dataclass
class SessionMedia:
    """Un lecteur declare aupres de Windows."""

    application: str      # ex: "Chrome", "Spotify"
    titre: str
    etat: int

    @property
    def joue(self) -> bool:
        return self.etat == EN_LECTURE


def _executer(coroutine):
    """Execute une coroutine WinRT depuis du code synchrone."""
    import asyncio

    try:
        boucle = asyncio.new_event_loop()
        try:
            return boucle.run_until_complete(coroutine)
        finally:
            boucle.close()
    except Exception as exc:
        log.debug("Appel WinRT impossible : %s", exc)
        return None


def _gestionnaire():
    """Gestionnaire de sessions media, ou None si indisponible."""
    try:
        from winsdk.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Gestionnaire,
        )
    except ImportError:
        return None
    return _executer(Gestionnaire.request_async())


def sessions() -> list:
    """Liste les lecteurs actuellement declares au systeme."""
    gestionnaire = _gestionnaire()
    if gestionnaire is None:
        return []
    resultat = []
    try:
        for session in gestionnaire.get_sessions():
            try:
                proprietes = _executer(session.try_get_media_properties_async())
                titre = getattr(proprietes, "title", "") or ""
            except Exception:
                titre = ""
            etat = session.get_playback_info().playback_status
            resultat.append(
                SessionMedia(str(session.source_app_user_model_id), titre, int(etat))
            )
    except Exception as exc:
        log.debug("Lecture des sessions impossible : %s", exc)
    return resultat


def _session_brute(application: str):
    """Retrouve l objet session WinRT correspondant a une application."""
    gestionnaire = _gestionnaire()
    if gestionnaire is None:
        return None
    cible = _simplifier(application)
    try:
        for session in gestionnaire.get_sessions():
            if _simplifier(str(session.source_app_user_model_id)) == cible:
                return session
    except Exception:
        return None
    return None


def _simplifier(nom: str) -> str:
    """« chrome.exe », « Chrome » et « Google Chrome » doivent se correspondre."""
    nom = (nom or "").lower().strip()
    for suffixe in (".exe", ".appx"):
        if nom.endswith(suffixe):
            nom = nom[: -len(suffixe)]
    return nom.replace("google ", "").replace("mozilla ", "").strip()


def correspond(processus: str, application_session: str) -> bool:
    """Le processus d une fenetre correspond-il a une session media ?"""
    a, b = _simplifier(processus), _simplifier(application_session)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------
def _agir_sur_session(application: str, action: str) -> bool:
    """Applique une action a une session precise (pause, play, bascule...)."""
    session = _session_brute(application)
    if session is None:
        return False
    methodes = {
        "pause": "try_pause_async",
        "play": "try_play_async",
        "bascule": "try_toggle_play_pause_async",
        "suivant": "try_skip_next_async",
        "precedent": "try_skip_previous_async",
        "stop": "try_stop_async",
    }
    nom_methode = methodes.get(action)
    if nom_methode is None:
        return False
    try:
        return bool(_executer(getattr(session, nom_methode)()))
    except Exception as exc:
        log.debug("Action %s impossible sur %s : %s", action, application, exc)
        return False


def _pause_par_le_clavier(fenetre) -> bool:
    """
    Repli pour les lecteurs sans session media : on affiche la fenetre puis
    on envoie la touche pause. C est exactement ce que ferait l utilisateur.
    """
    if not desktop.mettre_au_premier_plan(fenetre.handle):
        return False
    # Les lecteurs web repondent a l espace ; « k » marche aussi sur YouTube.
    return win_utils.press_key(VK_ESPACE)


def basculer_tout() -> bool:
    """Lecture/pause sur le lecteur actif (comportement de la touche media)."""
    for session in sessions():
        if _agir_sur_session(session.application, "bascule"):
            return True
    return win_utils.press_key(win_utils.VK_MEDIA_PLAY_PAUSE)


def mettre_en_pause_tout() -> list:
    """Met en pause TOUS les lecteurs en cours. Retourne ceux arretes."""
    arretes = []
    for session in sessions():
        if session.joue and _agir_sur_session(session.application, "pause"):
            arretes.append(session)
    if not arretes:
        win_utils.press_key(win_utils.VK_MEDIA_PLAY_PAUSE)
    return arretes


def reprendre_tout() -> list:
    """Relance les lecteurs en pause."""
    repris = []
    for session in sessions():
        if not session.joue and _agir_sur_session(session.application, "play"):
            repris.append(session)
    if not repris:
        win_utils.press_key(win_utils.VK_MEDIA_PLAY_PAUSE)
    return repris


def agir_sur_ecran(index_ecran: int, action: str = "pause") -> tuple:
    """
    Applique une action de lecture a ce qui joue sur un ecran donne.

    Retourne (succes, description). On tente d abord les sessions media
    (precis, sans voler le focus), puis on retombe sur le clavier.
    """
    fenetres = desktop.fenetres_sur_ecran(index_ecran)
    if not fenetres:
        return False, "aucune fenêtre sur cet écran"

    liste_sessions = sessions()
    touchees = []

    # 1) Lecteurs declares : on vise l application exacte.
    for fenetre in fenetres:
        for session in liste_sessions:
            if not correspond(fenetre.processus, session.application):
                continue
            if action == "pause" and not session.joue:
                continue
            if action == "play" and session.joue:
                continue
            if _agir_sur_session(session.application, action):
                titre = session.titre or fenetre.titre
                touchees.append(session.application + " (" + titre[:45] + ")")
            break

    if touchees:
        return True, ", ".join(touchees)

    # 2) Repli : la fenetre la plus plausible, mise au premier plan.
    candidates = [f for f in fenetres if f.est_navigateur or f.est_lecteur]
    if not candidates:
        return False, "rien qui ressemble à une lecture sur cet écran"
    if _pause_par_le_clavier(candidates[0]):
        return True, candidates[0].titre[:60] + " (via le clavier)"
    return False, "je n'ai pas pu agir sur " + candidates[0].processus
