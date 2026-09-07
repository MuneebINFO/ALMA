"""
Musique et video : lecture, pause, ciblage par ecran ou par application.

Toutes ces commandes agissent sur le SEUL ecran de travail : celui nomme dans
la phrase, sinon celui ou l assistant se trouve. Une video qui joue sur un
autre ecran n est jamais touchee -- et s il n y a rien a piloter sur l ecran
courant, il n y a rien a faire.

Le pilotage passe par les SESSIONS MEDIA de Windows, qui exposent chaque
lecteur separement (Chrome, Firefox, Spotify...). « mets tout en pause » est
la seule commande volontairement globale : elle le dit.
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


def ecran_cible(ctx: CommandContext) -> int:
    """
    L ecran sur lequel agir : celui nomme dans la phrase, sinon celui ou
    l assistant travaille. Toute action de lecture reste confinee a cet
    ecran ; ce qui joue ailleurs n est jamais touche.
    """
    return numero_ecran(ctx) or getattr(ctx.assistant, "ecran_actif", 1) or 1


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
    # Sans numero explicite, on agit sur l ecran de travail : « mets pause »
    # apres « va sur l ecran 2 » vise bien l ecran 2.
    index = ecran_cible(ctx)
    ecrans = desktop.ecrans()
    if ecrans and index > len(ecrans):
        return Response.error(
            "Je ne vois que " + str(len(ecrans)) + " écran(s), pas d'écran " + str(index) + "."
        )
    ok, detail = media_control.agir_sur_ecran(index, "pause")
    if ok:
        return Response(text="Pause sur l'écran " + str(index) + " : " + detail + ".")
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
    index = ecran_cible(ctx)
    ok, detail = media_control.agir_sur_ecran(index, "play")
    if ok:
        return Response(text="Lecture reprise sur l'écran " + str(index) + " : " + detail + ".")
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
    return Response(text="J'ai mis en pause : " + noms + ".")


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
    index = ecran_cible(ctx)
    sessions = media_control.sessions_sur_ecran(index)
    en_cours = [s for s in sessions if s.joue]
    if not en_cours:
        if sessions:
            return Response(text="Rien ne joue sur l'écran " + str(index)
                                 + ", tout est en pause.")
        return Response(text="Aucune lecture en cours sur l'écran " + str(index) + ".")
    parties = [
        (s.titre or "un contenu") + " sur " + s.application for s in en_cours
    ]
    return Response(text="En cours : " + " ; ".join(parties) + ".")


@command(
    name="media_play_pause",
    patterns=[
        r"^(?:play|pause)$",
        r"^" + VERBES_PAUSE + r"\s*(?:la\s+)?(?:musique|video|lecture|le\s+son|ca|tout\s+ca)?$",
        r"^(?:reprend[s]?|continue|relance)\s*(?:la\s+)?(?:musique|video|lecture)?$",
        r"(?:appuie|clique)\s+sur\s+pause",
    ],
    keywords=[["pause"], ["pause", "musique"], ["pause", "video"]],
    category="Musique",
    description="Lecture ou pause du lecteur actif",
    examples=["pause", "play"],
    priority=86,
)
def media_play_pause(ctx: CommandContext) -> Response:
    """Bascule lecture/pause sur le lecteur actif."""
    index = ecran_cible(ctx)
    ok, detail = media_control.agir_sur_ecran(index, "bascule")
    if ok:
        return Response(text="C'est fait.", speak=False)
    return Response.error("Rien à piloter sur l'écran " + str(index) + " (" + detail + ").")


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
    index = ecran_cible(ctx)
    ok, detail = media_control.agir_sur_ecran(index, "suivant")
    if ok:
        return Response(text="Morceau suivant.", speak=False)
    return Response.error("Rien à faire défiler sur l'écran " + str(index) + " (" + detail + ").")


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
    index = ecran_cible(ctx)
    ok, detail = media_control.agir_sur_ecran(index, "precedent")
    if ok:
        return Response(text="Morceau précédent.", speak=False)
    return Response.error("Rien à faire défiler sur l'écran " + str(index) + " (" + detail + ").")


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


# Ce sur quoi peut porter une demande de lecture ou de pause.
# « son » est volontairement absent : « remets le son » veut dire retablir
# le volume, pas relancer la lecture.
OBJET_LECTURE = r"(?:video|videos|film|musique|chanson|lecture|serie|episode|podcast)"


@command(
    name="media_lecture",
    patterns=[
        # L objet doit terminer la phrase : « lance la video Interstellar »
        # reste une recherche, pas une commande de lecture.
        r"^(?:lance|lancer|joue|jouer|demarre|demarrer|relance|relancer|remet[s]?|"
        r"reprend[s]?|reprendre|continue|continuer)\s+"
        r"(?:la\s+|le\s+|l\s+)?" + OBJET_LECTURE + r"$",
        r"^(?:met[s]?|mettre)\s+(?:la\s+|le\s+)?" + OBJET_LECTURE + r"\s+en\s+(?:marche|lecture|route)$",
        r"^(?:appuie|appuyer)\s+sur\s+(?:le\s+bouton\s+)?(?:play|lecture)$",
    ],
    # Pas de mots-cles de secours ici : « lance » + « video » captureraient
    # « lance la video Interstellar », qui designe une video precise.
    category="Musique",
    description="Lancer la lecture de la vidéo ou de la musique",
    examples=["lance la vidéo", "reprends la lecture"],
    priority=93,
)
def media_lecture(ctx: CommandContext) -> Response:
    """Relance ce qui est en pause, sans basculer si ça joue déjà."""
    index = ecran_cible(ctx)
    ok, detail = media_control.agir_sur_ecran(index, "play")
    if ok:
        return Response(text="Lecture : " + detail + ".", speak=False)
    return Response.error("Rien à relancer sur l'écran " + str(index) + " (" + detail + ").")


@command(
    name="media_mettre_en_pause",
    patterns=[
        r"^(?:met[s]?|mettre)\s+(?:en\s+)?pause\s+(?:a\s+|sur\s+)?"
        r"(?:la\s+|le\s+|l\s+)?" + OBJET_LECTURE + r"$",
        r"^(?:met[s]?|mettre)\s+(?:la\s+|le\s+|l\s+)?" + OBJET_LECTURE + r"\s+en\s+pause$",
        r"^pause\s+(?:a\s+)?(?:la\s+|le\s+|l\s+)?" + OBJET_LECTURE + r"$",
        # « arrete la musique » aboutit ici : mettre en pause conserve la
        # position, ce qu un arret pur et simple perdait.
        r"^(?:arrete|arreter|stoppe|stopper|coupe|suspend[s]?)\s+"
        r"(?:la\s+|le\s+|l\s+)?" + OBJET_LECTURE + r"$",
    ],
    keywords=[["pause", "video"], ["pause", "musique"]],
    category="Musique",
    description="Mettre la vidéo ou la musique en pause",
    examples=["mets pause à la vidéo", "mets la vidéo en pause"],
    priority=93,
)
def media_mettre_en_pause(ctx: CommandContext) -> Response:
    """Met en pause sans relancer si c'était déjà arrêté."""
    index = ecran_cible(ctx)
    ok, detail = media_control.agir_sur_ecran(index, "pause")
    if ok:
        return Response(text="En pause : " + detail + ".", speak=False)
    return Response.error("Rien à mettre en pause sur l'écran " + str(index) + " (" + detail + ").")
