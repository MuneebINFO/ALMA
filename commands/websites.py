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


def termes_de_recherche(cle: str, entree) -> list:
    """Mots permettant de reconnaitre ce site dans un titre de fenetre."""
    termes = [cle]
    if isinstance(entree, dict):
        termes += list(entree.get("aliases") or [])
    # On garde les alias d un seul mot : « prime video » ne figure pas tel
    # quel dans un titre, mais « prime » oui.
    return [t for t in termes if t and " " not in t]


def ouvrir_ou_reutiliser(config, cle: str, url: str) -> tuple:
    """
    Affiche le site en reutilisant un onglet deja ouvert quand c est possible.

    Le titre d une fenetre de navigateur reflete son onglet ACTIF : si ce
    titre mentionne le site, l onglet est deja affiche et on se contente de
    ramener la fenetre au premier plan, puis d y naviguer. Sinon on ouvre
    normalement dans le navigateur par defaut.

    Retourne (succes, "reutilise" | "ouvert").
    """
    from core import desktop

    entree = (config.get("websites", {}) or {}).get(cle, {})
    for terme in termes_de_recherche(cle, entree):
        fenetre = desktop.trouver_fenetre(terme, navigateurs_seulement=True)
        if fenetre is None:
            continue
        if desktop.naviguer_dans_fenetre(fenetre, url):
            return True, "reutilise"
        # La fenetre existe mais le pilotage a echoue : au moins on l affiche.
        desktop.mettre_au_premier_plan(fenetre.handle)
        break
    return open_url(url), "ouvert"


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
    ok, mode = ouvrir_ou_reutiliser(ctx.config, key, url)
    if not ok:
        return Response.error("Je n'ai pas réussi à ouvrir " + url + ".")
    if mode == "reutilise":
        return Response(text="Je reprends l'onglet " + key + ".")
    return Response(text="J'ouvre " + key + ".")


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


# Verbes qui introduisent une recherche a l interieur d un site.
VERBES_CONTENU = (
    r"(?:mets?|met\s+moi|mets\s+moi|lance|lancer|joue|jouer|regarde|regarder|"
    r"cherche|chercher|recherche|rechercher|trouve|trouver|affiche|afficher|"
    r"ouvre|montre|montre\s+moi|play|search|find)"
)


# Sites traites par une commande dediee plus riche : Wikipedia lit le resume
# a voix haute, Claude recoit la question dans le presse-papiers. Les
# intercepter ici degraderait le service.
SITES_RESERVES = {"wikipedia", "claude", "chatgpt"}


def _site_connu(ctx: CommandContext) -> bool:
    """Guard : cible connue, et non reservee a une commande specialisee."""
    resolu = resolve_website(ctx.config, ctx.group("site"))
    return resolu is not None and resolu[0] not in SITES_RESERVES


@command(
    name="site_search",
    patterns=[
        # « va sur Netflix et mets Fast and Furious »
        r"^(?:va|vas|aller|ouvre|ouvrir|lance|lancer|passe)\s+(?:sur|a|dans|vers)?\s*"
        r"(?P<site>.+?)\s+(?:et|puis|pour)\s+" + VERBES_CONTENU + r"\s+(?P<query>.+)$",
        # « mets Fast and Furious sur Netflix »
        r"^" + VERBES_CONTENU + r"\s+(?P<query>.+)\s+sur\s+(?P<site>[\w\s+]+)$",
        # « sur Netflix, mets Fast and Furious »
        r"^sur\s+(?P<site>.+?)\s*,?\s+" + VERBES_CONTENU + r"\s+(?P<query>.+)$",
    ],
    category="Sites web",
    description="Ouvrir un site et y lancer une recherche",
    examples=["va sur Netflix et mets Fast and Furious", "mets lofi hip hop sur YouTube"],
    priority=97,
    guard=_site_connu,
)
def site_search(ctx: CommandContext) -> Response:
    """
    Affiche le site -- en reutilisant l onglet s il est deja ouvert -- puis y
    lance la recherche demandee.
    """
    from urllib.parse import quote_plus

    resolu = resolve_website(ctx.config, ctx.group("site"))
    if resolu is None:
        return Response.error("Je ne connais pas ce site.")
    cle, url = resolu
    requete = ctx.group("query").strip()
    if not requete:
        return Response.error("Que dois-je chercher sur " + cle + " ?")

    entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
    modele = entree.get("search_url") if isinstance(entree, dict) else None
    cible = modele.replace("{q}", quote_plus(requete)) if modele else url

    ok, mode = ouvrir_ou_reutiliser(ctx.config, cle, cible)
    if not ok:
        return Response.error("Je n'ai pas réussi à ouvrir " + cle + ".")
    if not modele:
        return Response(
            text="J'ouvre " + cle + ", mais je ne sais pas y chercher directement."
        )
    prefixe = "Je reprends l'onglet " + cle if mode == "reutilise" else "J'ouvre " + cle
    return Response(text=prefixe + " et je cherche « " + requete + " ».")
