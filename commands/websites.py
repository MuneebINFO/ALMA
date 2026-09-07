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


def afficher_site(config, cle: str, url: str, naviguer: bool = False) -> tuple:
    """
    Affiche un site en reutilisant ce qui est deja ouvert.

    Trois strategies, de la plus precise a la moins bonne :
      1. un ONGLET portant ce site existe (meme en arriere-plan) : on l active ;
      2. une FENETRE affiche deja ce site : on la ramene au premier plan ;
      3. sinon on ouvre normalement.

    `naviguer` distingue deux intentions :
      - « va sur YouTube » veut juste AFFICHER l onglet. Y naviguer rechargerait
        la page d accueil et interromprait la video en cours ;
      - « mets X sur YouTube » veut charger une recherche : la navigation est
        alors necessaire.

    Retourne (succes, "onglet" | "fenetre" | "ouvert").
    """
    from core import browser_tabs, desktop

    entree = (config.get("websites", {}) or {}).get(cle, {})
    termes = termes_de_recherche(cle, entree)

    # 1) Un onglet existe-t-il, y compris en arriere-plan ?
    onglet = browser_tabs.trouver_onglet(termes)
    if onglet is not None:
        desktop.mettre_au_premier_plan(onglet.fenetre.handle)
        if onglet.activer():
            if naviguer and not desktop.naviguer_dans_fenetre(onglet.fenetre, url):
                return open_url(url), "ouvert"
            return True, "onglet"

    # 2) Repli : une fenetre dont l onglet actif affiche deja le site.
    for terme in termes:
        fenetre = desktop.trouver_fenetre(terme, navigateurs_seulement=True)
        if fenetre is None:
            continue
        if not naviguer:
            return desktop.mettre_au_premier_plan(fenetre.handle), "fenetre"
        if desktop.naviguer_dans_fenetre(fenetre, url):
            return True, "fenetre"
        desktop.mettre_au_premier_plan(fenetre.handle)
        break

    # 3) Rien d ouvert : ouverture classique.
    return open_url(url), "ouvert"


def ouvrir_ou_reutiliser(config, cle: str, url: str) -> tuple:
    """Compatibilite : ancien nom, navigation systematique."""
    return afficher_site(config, cle, url, naviguer=True)


@command(
    name="open_website",
    patterns=[
        r"^" + OPEN_VERBS + r"\s+(?:le\s+site\s+)?(.+)$",
        r"^(?:va|vas|aller|retourne|reviens|passe|bascule)\s+(?:sur|a|vers|dans)\s+(.+)$",
        # Formulations centrees sur l onglet deja ouvert.
        r"^(?:affiche|montre|reprends|remets|ramene)\s*(?:moi)?\s+(?:l\s+)?(?:onglet|page|site)\s+(.+)$",
        r"^(?:onglet|page)\s+(.+)$",
        r"^(?:reviens|retourne)\s+(?:sur|a)\s+(.+)$",
    ],
    category="Sites web",
    description="Ouvrir un site web (YouTube, Gmail, GitHub, Netflix...)",
    examples=["ouvre YouTube", "va sur l'onglet YouTube", "bascule sur Netflix"],
    priority=55,
    guard=_is_known_site,
)
def open_website(ctx: CommandContext) -> Response:
    """Ouvre un site declare dans la configuration."""
    resolved = resolve_website(ctx.config, ctx.arg)
    if resolved is None:
        return Response.error("Je ne connais pas ce site.")
    key, url = resolved
    # On retient le site : « recherche Damso » juste apres devra s y appliquer.
    ctx.assistant.memoriser("site", key)
    ok, mode = afficher_site(ctx.config, key, url, naviguer=False)
    if not ok:
        return Response.error("Je n'ai pas réussi à ouvrir " + url + ".")
    if mode == "onglet":
        return Response(text="Je bascule sur l'onglet " + key + ".")
    if mode == "fenetre":
        return Response(text="Je reviens sur " + key + ".")
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

    ctx.assistant.memoriser("site", cle)
    ok, mode = afficher_site(ctx.config, cle, cible, naviguer=True)
    if not ok:
        return Response.error("Je n'ai pas réussi à ouvrir " + cle + ".")
    if not modele:
        return Response(
            text="J'ouvre " + cle + ", mais je ne sais pas y chercher directement."
        )
    prefixe = ("Je reprends l'onglet " + cle) if mode != "ouvert" else ("J'ouvre " + cle)
    return Response(text=prefixe + " et je cherche « " + requete + " ».")


def _site_en_contexte(ctx: CommandContext) -> bool:
    """Guard : un site a-t-il ete ouvert recemment ?"""
    return bool(ctx.assistant.rappeler("site"))


@command(
    name="site_search_contextuel",
    patterns=[
        r"^(?:cherche|chercher|recherche|rechercher|trouve|trouver|met[s]?|joue|jouer|"
        r"lance|lancer|regarde|regarder|affiche|montre)\s+(?:moi\s+)?(.+)$",
    ],
    category="Sites web",
    description="Poursuivre sur le site en cours (« va sur YouTube » puis « recherche Damso »)",
    examples=["recherche Damso"],
    priority=85,
    guard=_site_en_contexte,
    contextuel=True,
)
def site_search_contextuel(ctx: CommandContext) -> Response:
    """
    Applique la recherche au site dont on vient de parler.

    C est ce qui permet d enchainer « va sur YouTube » puis « recherche
    Damso » sans repeter le nom du site. Le contexte expire avec la session
    d ecoute : passe ce delai, la meme phrase redevient une recherche web.
    """
    from urllib.parse import quote_plus

    cle = ctx.assistant.rappeler("site")
    requete = ctx.arg.strip()
    if not cle or not requete:
        return Response.error("Que dois-je chercher ?")

    entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
    modele = entree.get("search_url") if isinstance(entree, dict) else None
    if not modele:
        return Response.error("Je ne sais pas chercher directement sur " + cle + ".")

    cible = modele.replace("{q}", quote_plus(requete))
    ctx.assistant.memoriser("site", cle)          # on reste sur ce site
    ok, mode = afficher_site(ctx.config, cle, cible, naviguer=True)
    if not ok:
        return Response.error("Je n'ai pas réussi à chercher sur " + cle + ".")
    return Response(text="Je cherche « " + requete + " » sur " + cle + ".")


def _site_pour_nouvel_onglet(ctx: CommandContext) -> bool:
    """Guard : « ouvre un nouvel onglet » sans site reste un onglet vide."""
    return resolve_website(ctx.config, ctx.arg) is not None


@command(
    name="ouvrir_site_nouvel_onglet",
    patterns=[
        r"^(?:ouvre|ouvrir|lance|lancer)\s+(?:moi\s+)?(?:un\s+|dans\s+un\s+)?"
        r"nouvel?\s+onglet\s+(.+)$",
        r"^(?:ouvre|ouvrir)\s+(.+?)\s+dans\s+un\s+nouvel?\s+onglet$",
    ],
    category="Sites web",
    description="Ouvrir un site dans un nouvel onglet",
    examples=["ouvre un nouvel onglet YouTube"],
    priority=98,
    guard=_site_pour_nouvel_onglet,
)
def ouvrir_site_nouvel_onglet(ctx: CommandContext) -> Response:
    """
    Force un NOUVEL onglet, meme si le site est deja ouvert ailleurs.

    C est la difference avec « ouvre X » et « va sur X », qui reprennent
    l onglet existant plutot que d en empiler un de plus.
    """
    import webbrowser

    resolu = resolve_website(ctx.config, ctx.arg)
    if resolu is None:
        return Response.error("Je ne connais pas ce site.")
    cle, url = resolu
    ctx.assistant.memoriser("site", cle)
    try:
        ouvert = webbrowser.open_new_tab(url)
    except Exception:
        ouvert = False
    if ouvert:
        return Response(text="Nouvel onglet sur " + cle + ".", speak=False)
    return Response.error("Je n'ai pas réussi à ouvrir " + cle + ".")
