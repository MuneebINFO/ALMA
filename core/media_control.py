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

# Un navigateur est presque toujours ouvert : son titre seul dit s il affiche
# un lecteur. Sert a decider si le repli clavier est legitime.
SITES_MEDIA = (
    # plateformes
    "youtube", "netflix", "twitch", "prime video", "disney", "vimeo",
    "dailymotion", "crunchyroll", "molotov", "arte", "france.tv", "canal",
    "spotify", "deezer", "soundcloud", "plex", "apple music",
    # indices generiques : les sites de streaming sont innombrables, leur
    # titre trahit presque toujours ce qu ils affichent
    "anime", "manga", "stream", "replay", "film", "video", "episode",
    "saison", "vostfr", "lecteur", "player", "podcast",
)


def _titre_de_media(fenetre) -> bool:
    """La fenetre affiche-t-elle une page de lecture reconnaissable ?"""
    titre = (fenetre.titre or "").lower()
    return any(site in titre for site in SITES_MEDIA)


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


def _normaliser(texte: str) -> str:
    """Minuscules sans accents, pour comparer un titre de media a un titre de fenetre."""
    from core import text_utils

    return text_utils.normalize(texte or "").lower()


def _titres_se_recoupent(titre_session: str, titre_fenetre: str) -> bool:
    """
    Le titre du media apparait-il dans le titre de la fenetre ?

    Un navigateur affiche l onglet actif dans son titre : « Interstellar -
    YouTube - Google Chrome ». C est ce qui permet de savoir LAQUELLE des
    fenetres Chrome joue, quand il y en a une par ecran.
    """
    a, b = _normaliser(titre_session), _normaliser(titre_fenetre)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    # Titres tronques par Windows : on compare les premiers mots.
    mots = [m for m in a.split() if len(m) > 3][:4]
    return bool(mots) and sum(1 for m in mots if m in b) >= max(2, len(mots) - 1)


def sessions_sur_ecran(index_ecran: int) -> list:
    """
    Les lecteurs qui jouent sur un ecran donne.

    Une session media est declaree par application, pas par fenetre : Chrome
    n en expose qu une seule meme s il a une fenetre sur chaque ecran. On
    rattache donc chaque session a un ecran en croisant le processus ET le
    titre, faute de quoi « mets pause » sur l ecran 1 arreterait la video
    ouverte sur l ecran 2.
    """
    toutes = desktop.fenetres()
    sur_ecran = [f for f in toutes if f.ecran == index_ecran]
    retenues = []
    for session in sessions():
        candidates = [f for f in toutes if correspond(f.processus, session.application)]
        if not candidates:
            # Lecteur sans fenetre visible (Spotify reduit dans la zone de
            # notification) : il n appartient a aucun ecran, on le laisse
            # pilotable depuis celui ou l on travaille.
            retenues.append(session)
            continue
        ici = [f for f in candidates if f.ecran == index_ecran]
        if not ici:
            continue
        if len(candidates) == len(ici):
            # L application n est presente que sur cet ecran : aucun doute.
            retenues.append(session)
            continue
        # Plusieurs ecrans : seul le titre tranche.
        if any(_titres_se_recoupent(session.titre, f.titre) for f in ici):
            retenues.append(session)
    return retenues


def applications_sur_ecran(index_ecran: int) -> list:
    """
    Les processus qui font du son sur un ecran donne (« chrome.exe »...).

    Sert a regler le volume du seul lecteur visible ici, sans toucher aux
    autres applications ni au volume general.
    """
    toutes = desktop.fenetres()
    noms = []
    for session in sessions_sur_ecran(index_ecran):
        nom = session.application
        for fenetre in toutes:
            if fenetre.ecran == index_ecran and correspond(fenetre.processus, nom):
                nom = fenetre.processus
                break
        if nom not in noms:
            noms.append(nom)
    return noms


def agir_sur_ecran(index_ecran: int, action: str = "pause") -> tuple:
    """
    Applique une action de lecture a ce qui joue sur un ecran donne.

    Retourne (succes, description). Rien sur cet ecran signifie qu il n y a
    rien a faire : on ne touche jamais a un lecteur affiche ailleurs.
    """
    fenetres = desktop.fenetres_sur_ecran(index_ecran)
    if not fenetres:
        return False, "aucune fenêtre sur cet écran"

    touchees = []
    for session in sessions_sur_ecran(index_ecran):
        if action == "pause" and not session.joue:
            continue
        if action == "play" and session.joue:
            continue
        if _agir_sur_session(session.application, action):
            titre = session.titre or session.application
            touchees.append(session.application + " (" + titre[:45] + ")")

    if touchees:
        return True, ", ".join(touchees)

    # Repli clavier, uniquement pour ce qui ressemble vraiment a un lecteur :
    # envoyer « espace » a une fenetre au hasard ferait defiler une page.
    if action not in ("pause", "play", "bascule"):
        return False, "aucun lecteur sur cet écran"
    # Seules les fenetres qui ressemblent vraiment a un lecteur sont eligibles.
    # Envoyer « espace » a un navigateur au hasard ferait defiler la page que
    # l utilisateur est en train de lire ; s il n y a rien a mettre en pause
    # sur cet ecran, il n y a rien a faire. Les fenetres arrivent dans l ordre
    # d empilement : la premiere est celle que l utilisateur regarde.
    candidates = [f for f in fenetres if f.est_lecteur or _titre_de_media(f)]
    if not candidates:
        return False, "rien qui ressemble à une lecture sur cet écran"
    if _pause_par_le_clavier(candidates[0]):
        return True, candidates[0].titre[:60] + " (via le clavier)"
    return False, "je n'ai pas pu agir sur " + candidates[0].processus
