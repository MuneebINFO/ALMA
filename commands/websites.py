"""
Ouverture de sites web.

Meme principe que les applications : la table nom -> URL est dans
config.yaml (section `websites`) et donc extensible sans toucher au code.
Cette commande a une priorite plus basse que `open_app` : "ouvre X" tente
d abord'une application, puis un site web.
"""

from __future__ import annotations

import webbrowser

from core import text_utils
from core.context import CommandContext, Response
from core.registry import command

from commands.apps import OPEN_VERBS, clean_target


def resolve_website(config, spoken: str):
    """Retrouve le site correspondant a un nom parle. Retourne (cle, url)."""
    target = clean_target(spoken)
    if not target:
        return None
    sites = config.get("websites", {}) or {}
    alias_index = {}
    for key, entry in sites.items():
        url = entry.get("url") if isinstance(entry, dict) else str(entry)
        alias_index[text_utils.normalize(key).strip()] = (key, url)
        if isinstance(entry, dict):
            for alias in entry.get("aliases", []) or []:
                alias_index[text_utils.normalize(alias).strip()] = (key, url)
    if target in alias_index:
        return alias_index[target]
    best = text_utils.best_match(target, list(alias_index.keys()), threshold=0.85)
    return alias_index[best] if best else None


def _is_known_site(ctx: CommandContext) -> bool:
    """Guard : ne prend la main que si la cible est un site connu."""
    return resolve_website(ctx.config, ctx.arg) is not None


def open_url(url: str) -> bool:
    """Ouvre une URL dans le navigateur par defaut."""
    try:
        return webbrowser.open(url)
    except Exception:
        return False


@command(
    name="open_website",
    patterns=[
        r"^" + OPEN_VERBS + r"\s+(?:le\s+site\s+)?(.+)$",
        r"^(?:va|vas|aller)\s+sur\s+(.+)$",
    ],
    category="Sites web",
    description="Ouvrir un site web (YouTube, Gmail, GitHub, Netflix...)",
    examples=["ouvre YouTube", "va sur GitHub", "ouvre Gmail"],
    priority=55,
    guard=_is_known_site,
)
def open_website(ctx: CommandContext) -> Response:
    """Ouvre un site declare dans la configuration."""
    resolved = resolve_website(ctx.config, ctx.arg)
    if resolved is None:
        return Response.error("Je ne connais pas ce site.")
    key, url = resolved
    if open_url(url):
        return Response(text="J'ouvre " + key + ".")
    return Response.error("Je n'ai pas réussi à ouvrir " + url + ".")


@command(
    name="open_raw_url",
    patterns=[r"^" + OPEN_VERBS + r"\s+(?:le\s+site\s+)?((?:https?\s*:\s*)?[a-z0-9-]+\s+(?:com|fr|be|org|net|io|dev)(?:\s|$).*)$"],
    category="Sites web",
    description="Ouvrir une adresse web dictée (exemple.com)",
    examples=["ouvre exemple.com"],
    priority=58,
)
def open_raw_url(ctx: CommandContext) -> Response:
    """Ouvre une URL brute dictee par l'utilisateur."""
    # La normalisation a transforme les points en espaces : on les remet.
    raw = ctx.arg.strip()
    tokens = [t for t in text_utils.tokenize(text_utils.normalize(raw)) if t not in ("https", "http")]
    if not tokens:
        return Response.error("Je n'ai pas compris l'adresse.")
    url = "https://" + ".".join(tokens)
    if open_url(url):
        return Response(text="J'ouvre " + url + ".")
    return Response.error("Je n'ai pas réussi à ouvrir " + url + ".")


@command(
    name="list_websites",
    patterns=[r"(quels?|liste|list).*(sites?|websites?)"],
    category="Sites web",
    description="Lister les sites que je sais ouvrir",
    examples=["quels sites connais-tu"],
    priority=70,
)
def list_websites(ctx: CommandContext) -> Response:
    """Liste les sites configures."""
    sites = ctx.config.get("websites", {}) or {}
    return Response(
        text="Je connais " + str(len(sites)) + " sites : " + ", ".join(sorted(sites)) + ".",
        speak=False,
    )
