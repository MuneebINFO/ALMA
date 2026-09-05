"""
Musique et medias.

On pilote le lecteur actif (Spotify, YouTube, Windows Media...) via les
touches multimedia virtuelles de Windows : cela fonctionne avec n importe
quelle application, sans API ni cle.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from core import win_utils
from core.context import CommandContext, Response
from core.registry import command

MUSIC_EXTENSIONS = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac")


def music_folder(config) -> Path:
    """Dossier de musique configure, ou le dossier Musique de Windows."""
    configured = str(config.get("paths.music", "") or "")
    if configured:
        return Path(win_utils.expand(configured))
    return Path(win_utils.expand("%USERPROFILE%/Music"))


@command(
    name="media_play_pause",
    patterns=[
        r"^(?:play|pause|met\s+en\s+pause|mets\s+en\s+pause|reprend|reprends|continue)\b",
        r"(?:met|mets|arrete)\s+(?:la\s+)?musique\s+en\s+pause",
        r"^(?:musique|lecture)\s+(?:pause|play)$",
    ],
    keywords=[["pause", "musique"], ["pause"]],
    category="Musique",
    description="Lecture / pause du lecteur actif",
    examples=["pause", "mets la musique en pause"],
    priority=86,
)
def media_play_pause(ctx: CommandContext) -> Response:
    """Bascule lecture/pause."""
    if win_utils.press_key(win_utils.VK_MEDIA_PLAY_PAUSE):
        return Response(text="Lecture ou pause.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="media_next",
    patterns=[
        r"(?:chanson|morceau|musique|piste|titre)\s+suivante?",
        r"^(?:suivant|suivante|next|passe|zappe)\b",
        r"(?:passe|change)\s+(?:a\s+)?(?:la\s+)?(?:chanson|musique|piste)?\s*(?:suivante?)?$",
    ],
    keywords=[["musique", "suivante"], ["chanson", "suivante"]],
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
        r"(?:chanson|morceau|musique|piste|titre)\s+precedente?",
        r"^(?:precedent|precedente|retour|previous)\b",
    ],
    keywords=[["musique", "precedente"], ["chanson", "precedente"]],
    category="Musique",
    description="Revenir au morceau précédent",
    examples=["chanson precedente"],
    priority=87,
)
def media_previous(ctx: CommandContext) -> Response:
    """Morceau précédent."""
    if win_utils.press_key(win_utils.VK_MEDIA_PREV):
        return Response(text="Morceau précédent.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="media_stop",
    patterns=[r"(?:arrete|arreter|stoppe|coupe)\s+(?:la\s+)?(?:musique|lecture|le\s+son\s+du\s+lecteur)"],
    keywords=[["arrete", "musique"]],
    category="Musique",
    description="Arrêter la lecture",
    examples=["arrete la musique"],
    priority=88,
)
def media_stop(ctx: CommandContext) -> Response:
    """Arrete la lecture."""
    if win_utils.press_key(win_utils.VK_MEDIA_STOP):
        return Response(text="Lecture arrêtée.", speak=False)
    return Response.error("Je n'ai pas pu piloter le lecteur.")


@command(
    name="play_music",
    patterns=[
        r"^(?:joue|jouer|lance|mets|met|met\s+moi|mets\s+moi)\s+(?:de\s+la\s+|un\s+peu\s+de\s+|la\s+)?musique$",
        r"^(?:musique|de\s+la\s+musique)$",
    ],
    keywords=[["joue", "musique"], ["lance", "musique"]],
    category="Musique",
    description="Lancer la musique (dossier local, sinon Spotify)",
    examples=["mets de la musique"],
    priority=89,
)
def play_music(ctx: CommandContext) -> Response:
    """
    Joue un fichier au hasard du dossier musique.
    Si le dossier est vide ou absent, ouvre Spotify a la place.
    """
    folder = music_folder(ctx.config)
    tracks = []
    if folder.exists():
        for root, _dirs, files in os.walk(folder):
            for filename in files:
                if filename.lower().endswith(MUSIC_EXTENSIONS):
                    tracks.append(os.path.join(root, filename))
            if len(tracks) > 500:  # inutile de scanner une discotheque entiere
                break
    if tracks:
        track = random.choice(tracks)
        ok, detail = win_utils.launch([track])
        if ok:
            return Response(text="Je lance " + Path(track).stem + ".")
        return Response.error("Lecture impossible : " + detail)

    apps = ctx.config.get("applications", {}) or {}
    spotify = apps.get("spotify", {})
    ok, detail = win_utils.launch(spotify.get("paths", []) or [])
    if ok:
        return Response(text="Aucun fichier local trouvé : j'ouvre Spotify.")
    return Response.error(
        "Aucune musique dans " + str(folder) + " et Spotify est introuvable. "
        "Renseignez paths.music dans config.yaml."
    )
