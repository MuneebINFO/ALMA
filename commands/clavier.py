"""
Actions d edition : copier, coller, annuler, enregistrer, dicter du texte.

Ces commandes s appliquent a l application au premier plan, exactement comme
si l on appuyait soi-meme sur les touches.
"""

from __future__ import annotations

from core import win_utils
from core.context import CommandContext, Response
from core.registry import command


def _raccourci(ctx: CommandContext, libelle: str, *touches) -> Response:
    """Envoie un raccourci et repond sans commenter l evidence."""
    if win_utils.raccourci(*touches):
        return Response(text=libelle, speak=False)
    return Response.error("Je n'ai pas pu envoyer ce raccourci.")


@command(
    name="copier",
    patterns=[r"^(?:copie|copier|copie\s+ca|copiez)$",
              r"^(?:copie|copier)\s+(?:la\s+)?(?:selection|ligne|ceci|cela|ca)$"],
    keywords=[["copie", "selection"]],
    category="Édition",
    description="Copier la sélection",
    examples=["copie la sélection"],
    priority=88,
)
def copier(ctx: CommandContext) -> Response:
    """Ctrl+C sur l'application active."""
    return _raccourci(ctx, "Copié.", "ctrl", "c")


@command(
    name="coller",
    patterns=[r"^(?:colle|coller|colle\s+ca|collez)$",
              r"^(?:colle|coller)\s+(?:le\s+|la\s+)?(?:texte|presse\s*papiers?|ceci|cela|ca)$"],
    keywords=[["colle"]],
    category="Édition",
    description="Coller le presse-papiers",
    examples=["colle"],
    priority=88,
)
def coller(ctx: CommandContext) -> Response:
    """Ctrl+V sur l'application active."""
    return _raccourci(ctx, "Collé.", "ctrl", "v")


@command(
    name="couper_selection",
    patterns=[r"^(?:coupe|couper)\s+(?:la\s+)?(?:selection|le\s+texte|ceci|cela)$"],
    category="Édition",
    description="Couper la sélection",
    examples=["coupe la sélection"],
    priority=90,
)
def couper_selection(ctx: CommandContext) -> Response:
    """Ctrl+X. Prioritaire sur « coupe le son », qui vise le volume."""
    return _raccourci(ctx, "Coupé.", "ctrl", "x")


@command(
    name="annuler",
    patterns=[r"^(?:annule|annuler|undo)$",
              r"^(?:annule|annuler)\s+(?:la\s+derniere\s+action|ca|le\s+changement)$",
              r"^(?:reviens|revenir)\s+en\s+arriere$"],
    keywords=[["annule", "action"], ["undo"]],
    category="Édition",
    description="Annuler la dernière action",
    examples=["annule la dernière action"],
    priority=86,
)
def annuler(ctx: CommandContext) -> Response:
    """Ctrl+Z."""
    return _raccourci(ctx, "Annulé.", "ctrl", "z")


@command(
    name="refaire",
    patterns=[r"^(?:refais|refaire|retablis|retablir|redo)$",
              r"^(?:refais|retablis)\s+(?:la\s+derniere\s+action|ca)$"],
    keywords=[["retablis"], ["redo"]],
    category="Édition",
    description="Rétablir l'action annulée",
    examples=["rétablis"],
    priority=86,
)
def refaire(ctx: CommandContext) -> Response:
    """Ctrl+Y."""
    return _raccourci(ctx, "Rétabli.", "ctrl", "y")


@command(
    name="tout_selectionner",
    patterns=[r"(?:selectionne|selectionner|prend[s]?)\s+tout$",
              r"^tout\s+selectionner$"],
    keywords=[["selectionne", "tout"]],
    category="Édition",
    description="Tout sélectionner",
    examples=["sélectionne tout"],
    priority=92,
)
def tout_selectionner(ctx: CommandContext) -> Response:
    """Ctrl+A."""
    return _raccourci(ctx, "Tout sélectionné.", "ctrl", "a")


@command(
    name="enregistrer",
    patterns=[r"^(?:enregistre|enregistrer|sauvegarde|sauvegarder|sauve)\s*(?:le\s+fichier|ca|ceci)?$"],
    keywords=[["enregistre"], ["sauvegarde"]],
    category="Édition",
    description="Enregistrer le document",
    examples=["enregistre"],
    priority=88,
)
def enregistrer(ctx: CommandContext) -> Response:
    """Ctrl+S."""
    return _raccourci(ctx, "Enregistré.", "ctrl", "s")


@command(
    name="imprimer",
    patterns=[r"^(?:imprime|imprimer)\s*(?:ca|le\s+document|la\s+page)?$"],
    keywords=[["imprime"]],
    category="Édition",
    description="Ouvrir la boîte d'impression",
    examples=["imprime la page"],
    priority=88,
)
def imprimer(ctx: CommandContext) -> Response:
    """Ctrl+P."""
    return _raccourci(ctx, "Fenêtre d'impression ouverte.", "ctrl", "p")


@command(
    name="rechercher_dans_page",
    patterns=[r"^(?:recherche|rechercher|cherche|trouve)\s+dans\s+(?:la\s+)?page\s*(.*)$",
              r"^(?:ctrl\s+f|recherche\s+sur\s+la\s+page)$"],
    category="Édition",
    description="Rechercher dans la page affichée",
    examples=["cherche dans la page"],
    priority=94,
)
def rechercher_dans_page(ctx: CommandContext) -> Response:
    """Ctrl+F, puis saisit le terme s'il a été dicté."""
    if not win_utils.raccourci("ctrl", "f"):
        return Response.error("Je n'ai pas pu ouvrir la recherche.")
    terme = ctx.arg.strip() if ctx.match and ctx.match.lastindex else ""
    if terme:
        import time

        time.sleep(0.25)
        win_utils.type_text(terme)
        return Response(text="Je cherche « " + terme + " » dans la page.", speak=False)
    return Response(text="Recherche ouverte.", speak=False)


@command(
    name="dicter",
    patterns=[r"^(?:ecris|ecrire|tape|taper|saisis|note\s+ceci\s*:)\s+(.+)$"],
    category="Édition",
    description="Écrire un texte dans l'application active",
    examples=["écris bonjour tout le monde"],
    priority=87,
)
def dicter(ctx: CommandContext) -> Response:
    """Saisit le texte dicté là où se trouve le curseur."""
    texte = ctx.arg.strip()
    if not texte:
        return Response.error("Que dois-je écrire ?")
    if win_utils.type_text(texte):
        return Response(text="Écrit : " + texte, speak=False)
    return Response.error("Je n'ai pas pu écrire ce texte.")


@command(
    name="valider",
    patterns=[r"^(?:valide|valider|entree|confirme|ok\s+valide|appuie\s+sur\s+entree)$"],
    category="Édition",
    description="Appuyer sur Entrée",
    examples=["valide"],
    priority=88,
)
def valider(ctx: CommandContext) -> Response:
    """Touche Entrée."""
    return _raccourci(ctx, "Validé.", "entree")


@command(
    name="echapper",
    patterns=[r"^(?:echap|echappe|annule\s+ca|ferme\s+ca|quitte\s+ca)$"],
    category="Édition",
    description="Appuyer sur Échap",
    examples=["échap"],
    priority=88,
)
def echapper(ctx: CommandContext) -> Response:
    """Touche Échap."""
    return _raccourci(ctx, "Échap.", "echap")
