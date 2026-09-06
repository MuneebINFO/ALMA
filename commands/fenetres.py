"""
Fenetres, onglets et affichage : naviguer sans toucher au clavier.
"""

from __future__ import annotations

from core import win_utils
from core.context import CommandContext, Response
from core.registry import command


def _raccourci(libelle: str, *touches) -> Response:
    if win_utils.raccourci(*touches):
        return Response(text=libelle, speak=False)
    return Response.error("Je n'ai pas pu envoyer ce raccourci.")


@command(
    name="nouvel_onglet",
    patterns=[r"(?:ouvre|nouveau|nouvel|cree)\s+(?:un\s+)?(?:nouvel\s+)?onglet$",
              r"^nouvel\s+onglet$"],
    keywords=[["nouvel", "onglet"], ["nouveau", "onglet"]],
    category="Fenêtres",
    description="Ouvrir un nouvel onglet",
    examples=["ouvre un nouvel onglet"],
    priority=93,
)
def nouvel_onglet(ctx: CommandContext) -> Response:
    return _raccourci("Nouvel onglet.", "ctrl", "t")


@command(
    name="fermer_onglet",
    patterns=[r"(?:ferme|fermer)\s+(?:cet?\s+|l\s+)?onglet$",
              r"^(?:ferme|fermer)\s+la\s+page$"],
    keywords=[["ferme", "onglet"]],
    category="Fenêtres",
    description="Fermer l'onglet courant",
    examples=["ferme cet onglet"],
    priority=93,
)
def fermer_onglet(ctx: CommandContext) -> Response:
    return _raccourci("Onglet fermé.", "ctrl", "w")


@command(
    name="rouvrir_onglet",
    patterns=[r"(?:rouvre|rouvrir|restaure|recupere)\s+(?:l\s+)?onglet",
              r"(?:onglet|page)\s+(?:ferme|precedente)\s+(?:par\s+erreur)?"],
    keywords=[["rouvre", "onglet"]],
    category="Fenêtres",
    description="Rouvrir le dernier onglet fermé",
    examples=["rouvre l'onglet fermé"],
    priority=94,
)
def rouvrir_onglet(ctx: CommandContext) -> Response:
    return _raccourci("Onglet rouvert.", "ctrl", "shift", "t")


@command(
    name="onglet_suivant",
    patterns=[r"^onglet\s+suivant$", r"(?:passe|va)\s+a\s+l\s+onglet\s+suivant"],
    keywords=[["onglet", "suivant"]],
    category="Fenêtres",
    description="Passer à l'onglet suivant",
    examples=["onglet suivant"],
    priority=95,
)
def onglet_suivant(ctx: CommandContext) -> Response:
    return _raccourci("Onglet suivant.", "ctrl", "tab")


@command(
    name="onglet_precedent",
    patterns=[r"^onglet\s+precedent$", r"(?:reviens|retourne)\s+a\s+l\s+onglet\s+precedent"],
    keywords=[["onglet", "precedent"]],
    category="Fenêtres",
    description="Revenir à l'onglet précédent",
    examples=["onglet précédent"],
    priority=95,
)
def onglet_precedent(ctx: CommandContext) -> Response:
    return _raccourci("Onglet précédent.", "ctrl", "shift", "tab")


@command(
    name="rafraichir",
    patterns=[r"^(?:rafraichis|rafraichir|actualise|actualiser|recharge|recharger)\s*(?:la\s+page)?$"],
    keywords=[["actualise"], ["recharge"]],
    category="Fenêtres",
    description="Recharger la page",
    examples=["actualise la page"],
    priority=90,
)
def rafraichir(ctx: CommandContext) -> Response:
    return _raccourci("Page rechargée.", "f5")


@command(
    name="page_precedente",
    patterns=[r"^(?:page|retour)\s+(?:precedente|arriere)$",
              r"^(?:reviens|retourne|reviens\s+en)\s+(?:a\s+la\s+page\s+precedente|arriere)$"],
    keywords=[["page", "precedente"]],
    category="Fenêtres",
    description="Revenir à la page précédente",
    examples=["page précédente"],
    priority=95,
)
def page_precedente(ctx: CommandContext) -> Response:
    return _raccourci("Page précédente.", "alt", "gauche")


@command(
    name="page_suivante",
    patterns=[r"^page\s+suivante$", r"^(?:avance|va)\s+a\s+la\s+page\s+suivante$"],
    keywords=[["page", "suivante"]],
    category="Fenêtres",
    description="Aller à la page suivante",
    examples=["page suivante"],
    priority=95,
)
def page_suivante(ctx: CommandContext) -> Response:
    return _raccourci("Page suivante.", "alt", "droite")


@command(
    name="zoom_avant",
    patterns=[r"(?:zoom|agrandis|agrandir|grossis)\s*(?:avant|le\s+texte|la\s+page|plus)?$",
              r"(?:c\s+est\s+trop\s+petit|plus\s+gros)"],
    keywords=[["zoom", "avant"], ["agrandis", "texte"]],
    category="Fenêtres",
    description="Agrandir l'affichage",
    examples=["zoom avant"],
    priority=91,
)
def zoom_avant(ctx: CommandContext) -> Response:
    return _raccourci("Zoom avant.", "ctrl", "plus")


@command(
    name="zoom_arriere",
    patterns=[r"(?:dezoom|dezoome|reduis|rapetisse)\s*(?:la\s+page|le\s+texte)?$",
              r"zoom\s+arriere$", r"(?:c\s+est\s+trop\s+gros|plus\s+petit)"],
    keywords=[["zoom", "arriere"], ["reduis", "texte"]],
    category="Fenêtres",
    description="Réduire l'affichage",
    examples=["zoom arrière"],
    priority=91,
)
def zoom_arriere(ctx: CommandContext) -> Response:
    return _raccourci("Zoom arrière.", "ctrl", "moins")


@command(
    name="zoom_normal",
    patterns=[r"(?:remet[s]?|remettre|reinitialise)\s+(?:le\s+)?zoom",
              r"^zoom\s+(?:normal|par\s+defaut|cent\s+pour\s+cent)$",
              r"(?:taille|zoom)\s+normale?$"],
    keywords=[["zoom", "normal"]],
    category="Fenêtres",
    description="Revenir au zoom normal",
    examples=["zoom normal"],
    priority=93,
)
def zoom_normal(ctx: CommandContext) -> Response:
    return _raccourci("Zoom réinitialisé.", "ctrl", "zero")


@command(
    name="plein_ecran",
    patterns=[r"(?:met[s]?|passe|mettre)\s+(?:en\s+)?plein\s+ecran",
              r"^plein\s+ecran$", r"(?:quitte|sors\s+du)\s+plein\s+ecran"],
    keywords=[["plein", "ecran"]],
    category="Fenêtres",
    description="Basculer en plein écran",
    examples=["plein écran"],
    priority=96,
)
def plein_ecran(ctx: CommandContext) -> Response:
    return _raccourci("Plein écran.", "f11")


@command(
    name="minimiser",
    patterns=[r"(?:minimise|minimiser|reduis|reduire|cache)\s+(?:la\s+|cette\s+)?fenetre",
              r"^(?:minimise|reduis)$"],
    keywords=[["minimise", "fenetre"]],
    category="Fenêtres",
    description="Réduire la fenêtre active",
    examples=["minimise la fenêtre"],
    priority=94,
)
def minimiser(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre réduite.", "win", "bas")


@command(
    name="agrandir_fenetre",
    patterns=[r"(?:agrandis|agrandir|maximise|maximiser)\s+(?:la\s+|cette\s+)?fenetre"],
    keywords=[["agrandis", "fenetre"], ["maximise"]],
    category="Fenêtres",
    description="Agrandir la fenêtre active",
    examples=["agrandis la fenêtre"],
    priority=94,
)
def agrandir_fenetre(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre agrandie.", "win", "haut")


@command(
    name="fermer_fenetre",
    patterns=[r"(?:ferme|fermer)\s+(?:la\s+|cette\s+)?fenetre$"],
    keywords=[["ferme", "fenetre"]],
    category="Fenêtres",
    description="Fermer la fenêtre active",
    examples=["ferme la fenêtre"],
    priority=94,
)
def fermer_fenetre(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre fermée.", "alt", "f4")


@command(
    name="changer_fenetre",
    patterns=[r"(?:change|changer|bascule|passe)\s+(?:de\s+|a\s+la\s+)?fenetre",
              r"^(?:fenetre\s+suivante|alt\s+tab)$"],
    keywords=[["change", "fenetre"]],
    category="Fenêtres",
    description="Passer à la fenêtre suivante",
    examples=["change de fenêtre"],
    priority=94,
)
def changer_fenetre(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre suivante.", "alt", "tab")


@command(
    name="afficher_bureau",
    patterns=[r"(?:affiche|montre|va\s+sur|retourne\s+sur)\s+(?:le\s+)?bureau$",
              r"(?:reduis|minimise)\s+tout$"],
    keywords=[["affiche", "bureau"]],
    category="Fenêtres",
    description="Afficher le bureau",
    examples=["affiche le bureau"],
    priority=96,
)
def afficher_bureau(ctx: CommandContext) -> Response:
    return _raccourci("Bureau affiché.", "win", "d")


@command(
    name="capture_zone",
    patterns=[r"(?:capture|capturer|prend[s]?)\s+(?:une\s+)?(?:zone|partie|selection|region)",
              r"capture\s+d\s+ecran\s+partielle"],
    keywords=[["capture", "zone"]],
    category="Fenêtres",
    description="Capturer une zone de l'écran",
    examples=["capture une zone"],
    priority=96,
)
def capture_zone(ctx: CommandContext) -> Response:
    """Ouvre l'outil de capture de Windows pour sélectionner une région."""
    if win_utils.raccourci("win", "shift", "s"):
        return Response(text="Sélectionnez la zone à capturer.", speak=False)
    return Response.error("Je n'ai pas pu ouvrir l'outil de capture.")
