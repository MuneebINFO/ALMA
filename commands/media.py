"""
Musique et video : lecture, pause, ciblage par ecran ou par application.

Deux niveaux de controle :
  - les SESSIONS MEDIA de Windows, qui exposent chaque lecteur separement
    (Chrome, Firefox, Spotify...) et permettent de viser precisement ;
  - les touches multimedia globales, en repli.

C est ce qui rend possible « mets pause sur l ecran 2 » : on regarde quelles
fenetres sont sur cet ecran, on retrouve le lecteur correspondant, et on ne
met en pause que celui-la.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from core import desktop, media_control, text_utils, win_utils
from core.context import CommandContext, Response
from core.registry import command

MUSIC_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac", ".opus")

# Nombres ecrits en toutes lettres, pour « le deuxieme ecran ».
ORDINAUX = {
    "premier": 1, "premiere": 1, "un": 1, "1er": 1,
    "deuxieme": 2, "second": 2, "seconde": 2, "deux": 2, "2eme": 2,
    "troisieme": 3, "trois": 3, "3eme": 3,
    "quatrieme": 4, "quatre": 4,
}

VERBES_PAUSE = r"(?:pause|met[s]?\s+en\s+pause|mettre\s+en\s+pause|stoppe|stopper|arrete|arreter|coupe|couper|suspend|suspendre|freeze|gele)"
VERBES_REPRISE = r"(?:reprend|reprends|reprendre|relance|relancer|continue|continuer|remet[s]?|redemarre|play|joue|reprise)"


def music_folder(config) -> Path:
    """Dossier de musique configure, ou le dossier Musique de Windows."""
    configure = str(config.get("paths.music", "") or "")
    return Path(win_utils.expand(configure or "%USERPROFILE%/Music"))


def numero_ecran(ctx: CommandContext) -> int | None:
    """
    Extrait le numero d ecran d une phrase : « ecran 2 », « deuxieme ecran »,
    « ecran de droite », « autre ecran ».
    """
    tokens = ctx.tokens
    for i, token in enumerate(tokens):
        if token.isdigit() and 1 <= int(token) <= 9:
            return int(token)
        if token in ORDINAUX:
            return ORDINAUX[token]

    ecrans = desktop.ecrans()
    if any(text_utils.fuzzy_in(mot, tokens) for mot in ("droite", "droit")):
        return len(ecrans) if ecrans else None
    if text_utils.fuzzy_in("gauche", tokens):
        return 1
    if any(text_utils.fuzzy_in(mot, tokens) for mot in ("principal", "principale")):
        return 1
    if text_utils.fuzzy_in("autre", tokens):
        # « l autre ecran » : celui qui n affiche pas la fenetre active.
        return 2 if len(ecrans) > 1 else None
    return None


@command(
    name="media_pause_ecran",
    patterns=[
        VERBES_PAUSE + r".*\b(?:ecran|moniteur|screen|affichage)\b",
        r"\b(?:ecran|moniteur|screen)\b.*" + VERBES_PAUSE,
    ],
    keywords=[["pause", "ecran"], ["stoppe", "ecran"], ["arrete", "ecran"]],
    category="Musique",
    description="Mettre en pause ce qui joue sur un écran précis",
    examples=["mets pause sur l'écran 2", "arrête la vidéo sur le deuxième écran"],
    priority=97,
)
def media_pause_ecran(ctx: CommandContext) -> Response:
    """Met en pause uniquement le lecteur affiché sur l'écran demandé."""
    index = numero_ecran(ctx)
    ecrans = desktop.ecrans()
    if index is None:
        return Response.error(
            "Quel écran ? Vous en avez " + str(len(ecrans)) + ". Dites « écran 1 » ou « écran 2 »."
        )
    if index > len(ecrans):
        return Response.error(
            "Je ne vois que " + str(len(ecrans)) + " écran(s), pas d'écran " + str(index) + "."
        )
    ok, detail = media_control.agir_sur_ecran(index, "pause")
    if ok:
        return Response.action("Pause sur l'écran " + str(index) + " : " + detail + ".")
    return Response.error("Rien à mettre en pause sur l'écran " + str(index) + " (" + detail + ").")


@command(
    name="media_reprise_ecran",
    patterns=[
        VERBES_REPRISE + r".*\b(?:ecran|moniteur|screen)\b",
        r"\b(?:ecran|moniteur|screen)\b.*" + VERBES_REPRISE,
    ],
    keywords=[["reprends", "ecran"], ["relance", "ecran"]],
    category="Musique",
    description="Reprendre la lecture sur un écran précis",
    examples=["reprends la lecture sur l'écran 2"],
    priority=97,
)
def media_reprise_ecran(ctx: CommandContext) -> Response:
    """Relance le lecteur affiché sur l'écran demandé."""
    index = numero_ecran(ctx)
    if index is None:
        return Response.error("Quel écran ? Dites « écran 1 » ou « écran 2 ».")
    ok, detail = media_control.agir_sur_ecran(index, "play")
    if ok:
        return Response.action("Lecture reprise sur l'écran " + str(index) + " : " + detail + ".")
    return Response.error("Rien à relancer sur l'écran " + str(index) + " (" + detail + ").")


@command(
    name="media_pause_tout",
    patterns=[
        VERBES_PAUSE + r"\s+(?:tout|tous|la\s+lecture|toutes\s+les\s+videos|partout)",
        r"^(?:pause|silence)\s+(?:generale?|partout|tout)$",
        r"(?:met[s]?|mettre)\s+tout\s+en\s+pause",
    ],
    keywords=[["pause", "tout"], ["arrete", "tout"]],
    category="Musique",
    description="Mettre en pause tous les lecteurs à la fois",
    examples=["mets tout en pause", "pause partout"],
    priority=96,
)
def media_pause_tout(ctx: CommandContext) -> Response:
    """Met en pause chaque lecteur en cours, sur tous les écrans."""
    arretes = media_control.mettre_en_pause_tout()
    if not arretes:
        return Response(text="Rien ne jouait, mais j'ai envoyé la commande pause.", speak=False)
    noms = ", ".join(s.application for s in arretes)
    return Response.action("J'ai mis en pause : " + noms + ".")


@command(
    name="media_what_is_playing",
    patterns=[
        r"(?:qu\s+est\s+ce\s+qui\s+joue|qu\s+est\s+ce\s+qu\s+on\s+ecoute|"
        r"quelle?\s+(?:musique|chanson|video)\s+(?:joue|passe|est\s+en\s+cours)|"
        r"c\s+est\s+quoi\s+(?:cette|la)\s+(?:musique|chanson))",
        r"^(?:qu\s+est\s+ce\s+qui\s+passe)$",
    ],
    keywords=[["quoi", "joue"], ["quelle", "musique"]],
    category="Musique",
    description="Dire ce qui est en cours de lecture",
    examples=["qu'est-ce qui joue"],
    priority=95,
)
def media_what_is_playing(ctx: CommandContext) -> Response:
    """Annonce les lectures en cours, avec leur application."""
    sessions = media_control.sessions()
    en_cours = [s for s in sessions if s.joue]
    if not en_cours:
        if sessions:
            return Response(text="Rien ne joue actuellement, tout est en pause.")
        return Response(text="Aucune lecture en cours.")
    parties = [
        (s.titre or "un contenu") + " sur " + s.application for s in en_cours
    ]
    return Response(text="En cours : " + " ; ".join(parties) + ".")


@command(
    name="media_play_pause",
    patterns=[
        r"^(?:play|pause)$",
        r"^" + VERBES_PAUSE + r"\s*(?:la\s+)?(?:musique|video|lecture|le\s+son|ca|tout\s+ca)?$",
        r"(?:met[s]?|mettre)\s+(?:la\s+)?(?:musique|video|lecture)\s+en\s+pause",
        r"^(?:reprend[s]?|continue|relance)\s*(?:la\s+)?(?:musique|video|lecture)?$",
        r"(?:appuie|clique)\s+sur\s+pause",
    ],
    keywords=[["pause"], ["pause", "musique"], ["pause", "video"]],
    category="Musique",
    description="Lecture ou pause du lecteur actif",
    examples=["pause", "mets la musique en pause"],
    priority=86,
)
def media_play_pause(ctx: CommandContext) -> Response:
    """Bascule lecture/pause sur le lecteur actif."""
    if media_control.basculer_tout():
        return Response(text="C'est fait.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="media_next",
    patterns=[
        r"(?:chanson|morceau|musique|piste|titre|video|episode)\s+(?:d\s+apres|suivante?)",
        r"^(?:suivant|suivante|next|passe|zappe|skip)\b",
        r"(?:passe|change|saute)\s+(?:a\s+)?(?:la\s+|le\s+)?(?:chanson|musique|piste|titre|suite)?",
        r"(?:j\s+aime\s+pas|change)\s+(?:cette|de)\s+(?:chanson|musique)",
    ],
    keywords=[["musique", "suivante"], ["chanson", "suivante"], ["suivant"], ["skip"]],
    category="Musique",
    description="Passer au morceau suivant",
    examples=["chanson suivante", "suivant"],
    priority=87,
)
def media_next(ctx: CommandContext) -> Response:
    """Morceau suivant."""
    if win_utils.press_key(win_utils.VK_MEDIA_NEXT):
        return Response(text="Morceau suivant.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="media_previous",
    patterns=[
        r"(?:chanson|morceau|musique|piste|titre|video)\s+(?:d\s+avant|precedente?)",
        # « reviens » seul est ambigu (« reviens sur YouTube » vise un onglet) :
        # on ne le prend qu accompagne d un mot du champ lexical de la lecture.
        r"^(?:precedent|precedente|retour|previous)\b",
        r"^reviens\s+(?:en\s+arriere|au\s+debut|a\s+la\s+precedente)",
        r"(?:remet[s]?|repasse)\s+(?:la\s+)?(?:chanson|musique)\s+(?:d\s+avant|precedente)",
    ],
    keywords=[["musique", "precedente"], ["chanson", "precedente"], ["precedent"]],
    category="Musique",
    description="Revenir au morceau précédent",
    examples=["chanson précédente"],
    priority=87,
)
def media_previous(ctx: CommandContext) -> Response:
    """Morceau précédent."""
    if win_utils.press_key(win_utils.VK_MEDIA_PREV):
        return Response(text="Morceau précédent.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="media_stop",
    patterns=[
        r"(?:arrete|arreter|stoppe|stopper|coupe|couper|eteins)\s+(?:la\s+|le\s+)?(?:musique|lecture|video|son\s+du\s+lecteur)",
        r"^stop$",
    ],
    keywords=[["arrete", "musique"], ["stoppe", "musique"], ["arrete", "video"]],
    category="Musique",
    description="Arrêter la lecture",
    examples=["arrête la musique"],
    priority=88,
)
def media_stop(ctx: CommandContext) -> Response:
    """Arrête la lecture."""
    if win_utils.press_key(win_utils.VK_MEDIA_STOP):
        return Response(text="Lecture arrêtée.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="play_music",
    patterns=[
        r"^(?:joue|jouer|lance|lancer|met[s]?|met\s+moi|mets\s+moi|balance|envoie)\s+"
        r"(?:de\s+la\s+|un\s+peu\s+de\s+|la\s+|du\s+)?musique$",
        r"^(?:musique|de\s+la\s+musique|un\s+peu\s+de\s+musique)$",
        r"(?:j\s+ai\s+envie\s+de|on\s+met)\s+(?:de\s+la\s+)?musique",
    ],
    keywords=[["joue", "musique"], ["lance", "musique"], ["mets", "musique"]],
    category="Musique",
    description="Lancer la musique (dossier local, sinon Spotify)",
    examples=["mets de la musique"],
    priority=89,
)
def play_music(ctx: CommandContext) -> Response:
    """Joue un fichier au hasard du dossier musique, sinon ouvre Spotify."""
    dossier = music_folder(ctx.config)
    pistes = []
    if dossier.exists():
        for racine, _dossiers, fichiers in os.walk(dossier):
            for fichier in fichiers:
                if fichier.lower().endswith(MUSIC_EXTENSIONS):
                    pistes.append(os.path.join(racine, fichier))
            if len(pistes) > 500:
                break
    if pistes:
        piste = random.choice(pistes)
        ok, detail = win_utils.launch([piste])
        if ok:
            return Response(text="Je lance " + Path(piste).stem + ".")
        return Response.error("Lecture impossible : " + detail)

    apps = ctx.config.get("applications", {}) or {}
    ok, detail = win_utils.launch((apps.get("spotify", {}) or {}).get("paths", []) or [])
    if ok:
        return Response(text="Aucun fichier local trouvé : j'ouvre Spotify.")
    return Response.error(
        "Aucune musique dans " + str(dossier) + " et Spotify est introuvable. "
        "Renseignez paths.music dans config.yaml."
    )
