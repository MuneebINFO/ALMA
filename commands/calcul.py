"""
Calcul mental et tirages au sort.

L expression dictee est convertie en operation puis evaluee par une analyse
syntaxique RESTREINTE : seuls les nombres et les quatre operations sont
acceptes. Aucun code n est execute, meme si la phrase en contenait.
"""

from __future__ import annotations

import ast
import operator
import random
import re

from core import text_utils
from core.context import CommandContext, Response
from core.registry import command

# Operateurs dictes, du plus long au plus court pour eviter les recouvrements.
OPERATEURS = (
    ("divise par", "/"), ("divisee par", "/"), ("sur", "/"),
    ("multiplie par", "*"), ("multipliee par", "*"), ("fois", "*"),
    ("plus", "+"), ("moins", "-"), ("au carre", "**2"),
    ("plus que", "+"), ("plus de", "+"),
)

NOMBRES = {
    "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4,
    "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
    "seize": 16, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
    "soixante": 60, "cent": 100, "mille": 1000,
}

_NOEUDS_AUTORISES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod,
    ast.USub, ast.UAdd, ast.FloorDiv,
)
_OPERATIONS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def en_expression(texte: str) -> str:
    """Transforme une phrase dictee en expression arithmetique."""
    norme = " ".join(text_utils.tokenize(text_utils.normalize(texte)))
    for mot, symbole in OPERATEURS:
        norme = norme.replace(" " + mot + " ", " " + symbole + " ")
    mots = []
    for mot in norme.split():
        mots.append(str(NOMBRES[mot]) if mot in NOMBRES else mot)
    expression = " ".join(mots)
    # On ne garde que ce qui appartient a une operation.
    return re.sub(r"[^0-9+\-*/%.() ]", " ", expression).strip()


def evaluer(expression: str):
    """
    Evalue une expression arithmetique, et RIEN d autre.

    On parcourt l arbre syntaxique et on refuse tout noeud qui n est pas un
    nombre ou une operation : aucun appel de fonction, aucun nom de variable.
    """
    if not expression or not any(c.isdigit() for c in expression):
        return None
    try:
        arbre = ast.parse(expression, mode="eval")
    except SyntaxError:
        return None

    def visiter(noeud):
        if not isinstance(noeud, _NOEUDS_AUTORISES):
            raise ValueError("expression non autorisée")
        if isinstance(noeud, ast.Expression):
            return visiter(noeud.body)
        if isinstance(noeud, ast.Constant):
            if not isinstance(noeud.value, (int, float)):
                raise ValueError("constante non numérique")
            return noeud.value
        if isinstance(noeud, ast.UnaryOp):
            return _OPERATIONS[type(noeud.op)](visiter(noeud.operand))
        return _OPERATIONS[type(noeud.op)](visiter(noeud.left), visiter(noeud.right))

    try:
        return visiter(arbre)
    except (ValueError, KeyError, ZeroDivisionError, OverflowError, TypeError):
        return None


def formater(valeur) -> str:
    """Un resultat entier se dit sans decimales."""
    if isinstance(valeur, float) and abs(valeur - round(valeur)) < 1e-9:
        valeur = int(round(valeur))
    if isinstance(valeur, float):
        return ("%.4f" % valeur).rstrip("0").rstrip(".")
    return str(valeur)


@command(
    name="calculer",
    informatif=True,
    patterns=[
        r"^(?:combien\s+(?:font|fait|ca\s+fait)|calcule|calculer|resultat\s+de)\s+(.+)$",
        r"^(?:combien\s+ca\s+fait)\s+(.+)$",
        r"^(?:quel\s+est\s+le\s+resultat\s+de)\s+(.+)$",
    ],
    category="Informations",
    description="Faire un calcul",
    examples=["combien font 15 fois 4"],
    priority=94,
)
def calculer(ctx: CommandContext) -> Response:
    """Calcule une opération dictée."""
    expression = en_expression(ctx.arg)
    resultat = evaluer(expression)
    if resultat is None:
        return Response.error("Je n'ai pas su calculer cela.")
    return Response(text="Ça fait " + formater(resultat) + ".")


@command(
    name="pile_ou_face",
    informatif=True,
    patterns=[r"(?:pile\s+ou\s+face|lance\s+(?:une\s+)?piece|tire\s+a\s+pile\s+ou\s+face)"],
    keywords=[["pile", "face"]],
    category="Divers",
    description="Tirer à pile ou face",
    examples=["pile ou face"],
    priority=95,
)
def pile_ou_face(ctx: CommandContext) -> Response:
    return Response(text=random.choice(("Pile.", "Face.")))


@command(
    name="lancer_de",
    informatif=True,
    # « \b » en tete : sans lui, « balance de la musique » contient
    # « lance de » et declencherait un lancer de de.
    patterns=[r"\b(?:lance|jette|tire)\s+(?:un\s+|les\s+)?des?\b",
              r"^(?:un\s+)?de\s+a\s+(\d+)\s+faces?$"],
    keywords=[["lance", "de"]],
    category="Divers",
    description="Lancer un dé",
    examples=["lance un dé"],
    priority=95,
)
def lancer_de(ctx: CommandContext) -> Response:
    faces = 6
    for token in ctx.tokens:
        if token.isdigit() and 2 <= int(token) <= 1000:
            faces = int(token)
            break
    return Response(text="J'ai obtenu " + str(random.randint(1, faces)) + ".")


@command(
    name="nombre_aleatoire",
    informatif=True,
    patterns=[r"(?:un\s+)?(?:nombre|chiffre)\s+(?:au\s+hasard|aleatoire)\s*"
              r"(?:entre\s+(\d+)\s+et\s+(\d+))?",
              r"(?:tire|choisis|donne)\s+(?:moi\s+)?un\s+nombre\s+entre\s+(\d+)\s+et\s+(\d+)"],
    keywords=[["nombre", "hasard"]],
    category="Divers",
    description="Tirer un nombre au hasard",
    examples=["donne-moi un nombre entre 1 et 100"],
    priority=95,
)
def nombre_aleatoire(ctx: CommandContext) -> Response:
    bornes = [int(t) for t in ctx.tokens if t.isdigit()]
    debut, fin = (bornes[0], bornes[1]) if len(bornes) >= 2 else (1, 100)
    if debut > fin:
        debut, fin = fin, debut
    return Response(text=str(random.randint(debut, fin)) + ".")
