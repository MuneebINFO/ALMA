"""
Ouverture et fermeture d applications Windows.

La table nom parle -> executable vit dans config.yaml (section
`applications`), ce qui permet d en ajouter sans toucher au code.
"""

from __future__ import annotations

from core import text_utils, win_utils
from core.context import CommandContext, Response
from core.registry import command

# Mots parasites fréquents devant un nom d application.
_FILLERS = (
    "moi", "le", "la", "les", "l", "un", "une", "des", "mon", "ma", "mes",
    "the", "my", "app", "application", "logiciel", "programme", "stp",
    "onglet", "onglets", "page", "site", "tab", "fenetre",
    "s'il te plaît", "s il vous plait", "please",
)

OPEN_VERBS = r"(?:ouvre|ouvrir|ouvres|lance|lancer|lances|demarre|demarrer|execute|open|launch|start|run)"
CLOSE_VERBS = r"(?:ferme|fermer|fermes|quitte|quitter|tue|arrete|arreter|close|kill|stop)"


def clean_target(raw: str) -> str:
    """Retire les mots parasites autour du nom vise."""
    tokens = text_utils.tokenize(text_utils.normalize(raw))
    while tokens and tokens[0] in _FILLERS:
        tokens.pop(0)
    while tokens and tokens[-1] in _FILLERS:
        tokens.pop()
    return " ".join(tokens)


def resolve_app(config, spoken: str):
    """
    Retrouve l application correspondant a un nom parle.
    Retourne (cle, definition) ou None. Tolerant aux fautes de frappe.
    """
    target = clean_target(spoken)
    if not target:
        return None
    apps = config.get("applications", {}) or {}
    # Index alias -> cle (les alias longs sont testes en premier).
    alias_index = {}
    for key, entry in apps.items():
        alias_index[text_utils.normalize(key).strip()] = key
        for alias in entry.get("aliases", []) or []:
            alias_index[text_utils.normalize(alias).strip()] = key
    if target in alias_index:
        key = alias_index[target]
        return key, apps[key]
    best = text_utils.best_match(target, list(alias_index.keys()), threshold=0.82)
    if best:
        key = alias_index[best]
        return key, apps[key]
    return None


def _is_known_app(ctx: CommandContext) -> bool:
    """Guard : ne prend la main que si la cible est une application connue."""
    return resolve_app(ctx.config, ctx.arg) is not None


@command(
    name="open_app",
    patterns=[r"^" + OPEN_VERBS + r"\s+(.+)$"],
    category="Applications",
    description="Ouvrir une application (Chrome, Word, VS Code, Spotify...)",
    examples=["ouvre Chrome", "lance la calculatrice", "demarre VS Code"],
    priority=60,
    guard=_is_known_app,
)
def open_app(ctx: CommandContext) -> Response:
    """Ouvre une application declaree dans la configuration."""
    resolved = resolve_app(ctx.config, ctx.arg)
    if resolved is None:
        return Response.error("Je ne connais pas cette application.")
    key, entry = resolved
    label = (entry.get("aliases") or [key])[0]
    ok, detail = win_utils.launch(entry.get("paths", []) or [])
    if ok:
        return Response.action("J'ouvre " + label + ".")
    return Response.error(
        "Impossible d ouvrir " + label + ". Vérifiez le chemin dans config.yaml "
        "(applications." + key + ".paths). Détail : " + detail
    )


@command(
    name="close_app",
    patterns=[r"^" + CLOSE_VERBS + r"\s+(.+)$"],
    category="Applications",
    description="Fermer une application ouverte",
    examples=["ferme Chrome", "quitte Spotify"],
    priority=60,
    guard=_is_known_app,
)
def close_app(ctx: CommandContext) -> Response:
    """Ferme une application via son nom de processus."""
    resolved = resolve_app(ctx.config, ctx.arg)
    if resolved is None:
        return Response.error("Je ne connais pas cette application.")
    key, entry = resolved
    label = (entry.get("aliases") or [key])[0]
    process = entry.get("process", "")
    if not process:
        return Response.error(
            "Aucun processus n est configure pour " + label
            + " (applications." + key + ".process dans config.yaml)."
        )
    ok, detail = win_utils.kill_process(process)
    if ok:
        return Response.action("J'ai fermé " + label + ".")
    return Response.error(label + " ne semble pas ouvert. (" + detail + ")")


@command(
    name="list_apps",
    patterns=[r"(quelles?|liste|list).*(applications?|apps?|logiciels?)",
              r"^(?:liste|montre)\s+(?:les\s+)?apps?$"],
    category="Applications",
    description="Lister les applications que je sais ouvrir",
    examples=["quelles applications connais-tu", "liste les applications"],
    priority=70,
)
def list_apps(ctx: CommandContext) -> Response:
    """Liste les applications configurées."""
    apps = ctx.config.get("applications", {}) or {}
    names = sorted((entry.get("aliases") or [key])[0] for key, entry in apps.items())
    return Response(
        text="Je peux ouvrir " + str(len(names)) + " applications : " + ", ".join(names) + ".",
        speak=False,
    )
