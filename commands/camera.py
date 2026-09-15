"""
Commandes de la camera.

Ce fichier ne contient que ce qui releve de l AUTOMATISATION : allumer la
camera, prendre une image, la ranger. Comprendre ce qu il y a dessus est un
travail de modele, il vit ailleurs -- ici on se contente d appuyer sur le
declencheur.

Deux facons d avoir une image a l ecran, et elles ne servent pas a la meme
chose :

  - « ouvre la camera » lance l application Camera de Windows. On se voit,
    on se recadre, on cadre ce qu on veut montrer. C est un apercu ;
  - « prends une photo » capture sans rien afficher (voir core/camera.py) :
    l image est ecrite sur le disque, temoin eteint dans la foulee.

Il n y a pas d apercu integre a Alma, et c est un choix : l API de Windows
rend une image en une seconde environ, ce qui fait un diaporama, pas une
video. Mieux vaut l application du systeme, qui fait ca tres bien.
"""

from __future__ import annotations

from pathlib import Path

from core import camera
from core.context import CommandContext, Response
from core.registry import command


def _camera_branchee(ctx: CommandContext) -> bool:
    """Guard : sans camera, le routeur doit continuer a chercher."""
    return camera.disponible()


@command(
    name="camera_photo",
    patterns=[
        # « photo de l ecran » appartient a la capture d ecran : on l exclut
        # explicitement, les deux phrases se ressemblent trop.
        r"^(?:prend|prends|prendre|fais|faire)\s+(?:moi\s+)?(?:une\s+)?"
        r"photo(?:\s+(?:avec|de)\s+(?:la\s+|ma\s+)?(?:camera|webcam))?$",
        r"^(?:photo|selfie)$",
        r"^take\s+(?:a\s+)?(?:photo|picture|selfie)"
        r"(?:\s+with\s+(?:the\s+|my\s+)?(?:camera|webcam))?$",
    ],
    keywords=[["prends", "photo"], ["take", "photo"], ["take", "picture"]],
    category="Système",
    description="Prendre une photo avec la caméra",
    examples=["prends une photo", "take a photo"],
    priority=90,
    guard=_camera_branchee,
)
def camera_photo(ctx: CommandContext) -> Response:
    """Capture une image de la caméra et l enregistre."""
    image = camera.capturer()
    if not image:
        # Pas de camera, pilote absent, ou acces refuse dans les reglages de
        # confidentialite de Windows -- le cas le plus frequent, et celui
        # qu on ne peut pas distinguer d ici.
        return ctx.erreur(
            "Je n'arrive pas à utiliser la caméra. "
            "Vérifiez qu'elle est autorisée dans les paramètres de confidentialité.",
            "I can't use the camera. "
            "Check that it's allowed in your privacy settings.",
        )

    dossier = ctx.config.resolve_path("photos", "photos")
    ok, detail = camera.enregistrer(image, dossier)
    if not ok:
        return ctx.erreur("Photo non enregistrée : " + detail,
                          "Couldn't save the photo: " + detail)

    return ctx.reponse("Photo enregistrée : " + Path(detail).name,
                       "Photo saved: " + Path(detail).name)
