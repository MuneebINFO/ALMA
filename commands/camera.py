"""
Commandes de la camera.

PRENDRE une image releve de l automatisation, et c est gratuit. LA REGARDER
demande un modele, et c est l edition complete (voir core/edition.py). Les
deux vivent ici parce qu elles partagent la meme camera, mais la frontiere
passe au milieu du fichier et elle est dite a chaque fois.

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

import logging
from pathlib import Path

from core import camera
from core.context import CommandContext, Response
from core.registry import command

log = logging.getLogger(__name__)


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


# --------------------------------------------------------------------------
# Regarder -- edition complete
# --------------------------------------------------------------------------
# Les questions posees au modele. Courtes, et elles disent que la reponse
# sera LUE : un modele a qui l on ne precise rien repond par un paragraphe,
# et un paragraphe ne s ecoute pas.
QUESTION_MAIN = {
    "fr": "Que tient la personne dans sa main ? Réponds en une phrase, "
          "en nommant l'objet aussi précisément que tu peux.",
    "en": "What is the person holding in their hand? Answer in one sentence, "
          "naming the object as precisely as you can.",
}
QUESTION_SCENE = {
    "fr": "Décris ce que tu vois sur cette image, en une ou deux phrases.",
    "en": "Describe what you see in this image, in one or two sentences.",
}


def _regarder(ctx: CommandContext, questions: dict) -> Response:
    """
    Prend une image et la fait decrire. Le fond commun des deux commandes.

    L image part ENTIERE, sans recadrage. Un modele de vision retrouve tres
    bien une main dans un cadre : detourer avant d envoyer aurait coute cent
    quatre-vingts megaoctets de dependances pour economiser une fraction de
    centime par photo.
    """
    from core import ai_fallback, edition

    if not edition.est_complete(ctx.config):
        return ctx.erreur(edition.SANS_REGARD_FR, edition.SANS_REGARD_EN)

    image = camera.capturer()
    if not image:
        return ctx.erreur(
            "Je n'arrive pas à utiliser la caméra. "
            "Vérifiez qu'elle est autorisée dans les paramètres de confidentialité.",
            "I can't use the camera. "
            "Check that it's allowed in your privacy settings.",
        )

    provider = ai_fallback.get_provider(ctx.config)
    regarder = getattr(provider, "analyser_image", None)
    if regarder is None:
        # Un provider qui ne sait pas voir -- un modele local, par exemple.
        # La photo est prise, elle ne sera simplement pas decrite.
        return ctx.erreur(edition.SANS_REGARD_FR, edition.SANS_REGARD_EN)

    try:
        vu = regarder(image, questions.get(ctx.lang, questions["fr"]), ctx.lang)
    except Exception as exc:
        log.warning("Analyse d'image impossible : %s", exc)
        return ctx.erreur("Je n'ai pas réussi à analyser l'image : " + str(exc),
                          "I couldn't analyse the image: " + str(exc))

    if not vu:
        return ctx.erreur("Je n'ai rien pu en dire.", "I couldn't make anything of it.")
    return ctx.reponse(vu, vu)


@command(
    name="camera_analyser_main",
    informatif=True,
    patterns=[
        r"(?:analyse|analyser|regarde|regarder|identifie|identifier)\s+"
        r"(?:moi\s+)?(?:ce\s+|l\s+)?(?:que|objet)?\s*"
        r"(?:j\s+ai|que\s+je\s+tiens|dans\s+ma\s+main)",
        r"^(?:qu\s+est\s+ce\s+que|c\s+est\s+quoi)\s+"
        r"(?:je\s+tiens|ce\s+que\s+je\s+tiens|l\s+objet\s+dans\s+ma\s+main)",
        r"(?:what\s+am\s+i\s+holding|what\s+s?\s*(?:is\s+)?in\s+my\s+hand)",
        r"(?:analyse|analyze|identify)\s+(?:what\s+)?(?:i\s+m\s+|i\s+am\s+)?"
        r"(?:holding|in\s+my\s+hand)",
    ],
    keywords=[["analyse", "main"], ["regarde", "main"], ["tiens", "main"],
              ["holding"], ["analyse", "hand"]],
    category="Recherche",
    description="Analyser l'objet tenu dans la main",
    examples=["analyse ce que j'ai dans la main", "what am I holding"],
    priority=94,
    guard=_camera_branchee,
    attente="analyse",
)
def camera_analyser_main(ctx: CommandContext) -> Response:
    """Prend une photo et dit quel objet la personne tient."""
    return _regarder(ctx, QUESTION_MAIN)


@command(
    name="camera_decrire",
    informatif=True,
    patterns=[
        r"^(?:qu\s+est\s+ce\s+que\s+tu\s+vois|que\s+vois\s+tu)"
        r"(?:\s+(?:avec\s+)?(?:la\s+)?camera)?$",
        r"(?:regarde|regarder)\s+(?:avec\s+)?(?:la\s+|ma\s+)?camera$",
        r"^(?:what\s+do\s+you\s+see|what\s+can\s+you\s+see)"
        r"(?:\s+(?:with\s+)?(?:the\s+)?camera)?$",
        r"^look\s+(?:through\s+|with\s+)?(?:the\s+|my\s+)?camera$",
    ],
    keywords=[["vois", "camera"], ["see", "camera"]],
    category="Recherche",
    description="Décrire ce que voit la caméra",
    examples=["qu'est-ce que tu vois", "what do you see"],
    priority=92,
    guard=_camera_branchee,
    attente="analyse",
)
def camera_decrire(ctx: CommandContext) -> Response:
    """Prend une photo et décrit ce qui s y trouve."""
    return _regarder(ctx, QUESTION_SCENE)
