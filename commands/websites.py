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


def _chemin_chrome(config) -> str:
    """
    Le chemin de Chrome, ou une chaine vide.

    C est le seul navigateur qu on sait lancer depuis zero avec une adresse
    ET forcer dans une fenetre neuve (--new-window) -- c est deja ce que fait
    le mode IA de Google (core/providers/gemini_provider.py).
    """
    import os
    import shutil

    for candidat in list(config.get("applications.chrome.paths", []) or []) + ["chrome.exe"]:
        chemin = os.path.expandvars(str(candidat))
        if os.path.isfile(chemin):
            return chemin
    return shutil.which("chrome.exe") or ""


def _ouvrir_normalement(config, url: str, ecran) -> bool:
    """
    Ouvre l URL pour de bon : rien de ce qu on cherchait n etait deja affiche
    la ou l on travaille.

    Le navigateur PAR DEFAUT (`open_url`) ne garantit rien sur l ecran : s il
    tourne deja ailleurs, c est LUI qui decide dans quelle fenetre atterrir
    l adresse -- typiquement la derniere regardee, sur un autre ecran. C est
    exactement ce qui s est vu a l usage : « ouvre Google », dit depuis un
    ecran sans Chrome, ouvrait l onglet dans le Chrome de l autre ecran, sans
    rien montrer la ou on regardait.

    On force donc une fenetre Chrome TOUTE NEUVE (--new-window) et on l amene
    sur l ecran de travail, comme pour une application (voir
    apps.py:_placer). Le navigateur par defaut ne reste un repli que si
    Chrome est introuvable, ou que l ecran est inconnu.
    """
    import subprocess

    from core import desktop

    chemin = _chemin_chrome(config)
    if not chemin or ecran is None:
        return open_url(url)

    connues = desktop.poignees_visibles()
    try:
        subprocess.Popen(
            [chemin, "--new-window", url],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return open_url(url)

    fenetre = desktop.attendre_nouvelle_fenetre(connues, processus="chrome.exe")
    if fenetre is not None and fenetre.ecran != ecran:
        desktop.deplacer_vers_ecran(fenetre.handle, ecran)
    return True


def termes_de_recherche(cle: str, entree) -> list:
    """Mots permettant de reconnaitre ce site dans un titre de fenetre."""
    termes = [cle]
    if isinstance(entree, dict):
        termes += list(entree.get("aliases") or [])
    # On garde les alias d un seul mot : « prime video » ne figure pas tel
    # quel dans un titre, mais « prime » oui.
    return [t for t in termes if t and " " not in t]


def afficher_site(config, cle: str, url: str, naviguer: bool = False,
                  assistant=None) -> tuple:
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
    ecran = getattr(assistant, "ecran_actif", None) if assistant is not None else None

    # 1) Un onglet existe-t-il, y compris en arriere-plan ?
    onglet = browser_tabs.trouver_onglet(termes, ecran=ecran)
    if onglet is not None:
        desktop.mettre_au_premier_plan(onglet.fenetre.handle)
        if onglet.activer():
            if naviguer and not desktop.naviguer_dans_fenetre(onglet.fenetre, url):
                return open_url(url), "ouvert"
            return True, "onglet"

    # 2) Repli : une fenetre dont l onglet actif affiche deja le site.
    for terme in termes:
        fenetre = desktop.trouver_fenetre(terme, navigateurs_seulement=True, ecran=ecran)
        if fenetre is None:
            continue
        if not naviguer:
            return desktop.mettre_au_premier_plan(fenetre.handle), "fenetre"
        if desktop.naviguer_dans_fenetre(fenetre, url):
            return True, "fenetre"
        desktop.mettre_au_premier_plan(fenetre.handle)
        break

    # 3) Rien d ouvert sur l ecran de travail : ouverture toute neuve, la.
    return _ouvrir_normalement(config, url, ecran), "ouvert"


def ouvrir_ou_reutiliser(config, cle: str, url: str) -> tuple:
    """Compatibilite : ancien nom, navigation systematique."""
    return afficher_site(config, cle, url, naviguer=True)


# « ouvre » et « va sur » ne demandent pas la meme chose. Ouvrir, c est
# arriver sur le site ; y aller, c est retrouver l onglet ou l on etait.
# La nuance compte : un onglet « Tik Tok - Recherche Google » porte le nom
# de Google sans etre Google, et le reprendre donnait l impression que rien
# ne se passait.
VERBES_D_OUVERTURE = ("ouvre", "ouvrir", "ouvres", "lance", "lancer", "lances",
                      "demarre", "demarrer", "open", "launch", "start")


def _demande_une_ouverture(ctx: CommandContext) -> bool:
    mots = text_utils.tokenize(text_utils.normalize(ctx.raw))
    return bool(mots) and mots[0] in VERBES_D_OUVERTURE


def _nouvel_onglet(ctx: CommandContext, url: str) -> bool:
    """
    Un onglet de plus, sur l ECRAN DE TRAVAIL : dans le navigateur qui y est
    deja si possible, sinon dans une fenetre toute neuve -- jamais dans une
    fenetre d un autre ecran, meme si Chrome n y tourne qu une fois.
    """
    from core import desktop

    ecran = getattr(ctx.assistant, "ecran_actif", None)
    fenetre = desktop.trouver_fenetre("", navigateurs_seulement=True, ecran=ecran)
    if fenetre is not None and desktop.ouvrir_onglet(fenetre, url):
        return True
    return _ouvrir_normalement(ctx.config, url, ecran)


@command(
    name="open_website",
    patterns=[
        r"^" + OPEN_VERBS + r"\s+(?:le\s+site\s+)?(.+)$",
        r"^(?:va|vas|aller|retourne|reviens|passe|bascule)\s+(?:sur|a|vers|dans)\s+(.+)$",
        # Formulations centrees sur l onglet deja ouvert.
        r"^(?:affiche|montre|reprends|remets|ramene)\s*(?:moi)?\s+(?:l\s+)?(?:onglet|page|site)\s+(.+)$",
        r"^(?:onglet|page)\s+(.+)$",
        r"^(?:reviens|retourne)\s+(?:sur|a)\s+(.+)$",
        # « go to YouTube », « switch to Netflix », « back to Netflix »
        r"^(?:go|switch|come\s+back)\s+(?:to|back\s+to)\s+(.+)$",
        r"^(?:show|tab)\s+(.+)$",
    ],
    category="Sites web",
    description="Ouvrir un site web (YouTube, Gmail, GitHub, Netflix...)",
    examples=["ouvre YouTube", "va sur l'onglet YouTube", "bascule sur Netflix",
              "go to YouTube"],
    priority=55,
    guard=_is_known_site,
)
def open_website(ctx: CommandContext) -> Response:
    """Ouvre un site declare dans la configuration."""
    resolved = resolve_website(ctx.config, ctx.arg)
    if resolved is None:
        return ctx.erreur("Je ne connais pas ce site.", "I don't know that site.")
    key, url = resolved
    # On retient le site : « recherche Damso » juste apres devra s y appliquer.
    ctx.assistant.memoriser("site", key)

    if _demande_une_ouverture(ctx):
        if _nouvel_onglet(ctx, url):
            return ctx.reponse("J'ouvre " + key + ".", "Opening " + key + ".")
        return ctx.erreur("Je n'ai pas réussi à ouvrir " + key + ".",
                          "I couldn't open " + key + ".")

    ok, mode = afficher_site(ctx.config, key, url, naviguer=False, assistant=ctx.assistant)
    if not ok:
        return ctx.erreur("Je n'ai pas réussi à ouvrir " + url + ".",
                          "I couldn't open " + url + ".")
    if mode == "onglet":
        return ctx.reponse("Je bascule sur l'onglet " + key + ".",
                           "Switching to the " + key + " tab.")
    if mode == "fenetre":
        return ctx.reponse("Je reviens sur " + key + ".", "Back on " + key + ".")
    return ctx.reponse("J'ouvre " + key + ".", "Opening " + key + ".")


@command(
    name="open_raw_url",
    patterns=[r"^" + OPEN_VERBS + r"\s+(?:le\s+site\s+)?((?:https?\s*:\s*)?[a-z0-9-]+\s+(?:com|fr|be|org|net|io|dev)(?:\s|$).*)$"],
    category="Sites web",
    description="Ouvrir une adresse web dictée (exemple.com)",
    examples=["ouvre exemple.com", "open example.com"],
    priority=58,
)
def open_raw_url(ctx: CommandContext) -> Response:
    """Ouvre une URL brute dictee par l'utilisateur."""
    # La normalisation a transforme les points en espaces : on les remet.
    raw = ctx.arg.strip()
    tokens = [t for t in text_utils.tokenize(text_utils.normalize(raw)) if t not in ("https", "http")]
    if not tokens:
        return ctx.erreur("Je n'ai pas compris l'adresse.",
                          "I didn't catch the address.")
    url = "https://" + ".".join(tokens)
    if open_url(url):
        return ctx.reponse("J'ouvre " + url + ".", "Opening " + url + ".")
    return ctx.erreur("Je n'ai pas réussi à ouvrir " + url + ".",
                      "I couldn't open " + url + ".")


@command(
    name="list_websites",
    informatif=True,
    patterns=[r"(quels?|liste|list).*(sites?|websites?)"],
    category="Sites web",
    description="Lister les sites que je sais ouvrir",
    examples=["quels sites connais-tu", "list websites"],
    priority=70,
)
def list_websites(ctx: CommandContext) -> Response:
    """Liste les sites configures."""
    sites = ctx.config.get("websites", {}) or {}
    liste = ", ".join(sorted(sites))
    return ctx.reponse(
        "Je connais " + str(len(sites)) + " sites : " + liste + ".",
        "I know " + str(len(sites)) + " sites: " + liste + ".",
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


def fenetre_du_site(ctx: CommandContext, cle: str):
    """La fenetre qui affiche deja ce site, ou None."""
    from core import browser_tabs, desktop

    entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
    termes = termes_de_recherche(cle, entree)
    ecran = getattr(ctx.assistant, "ecran_actif", None)
    onglet = browser_tabs.trouver_onglet(termes, ecran=ecran)
    if onglet is not None:
        return onglet.fenetre
    for terme in termes:
        fenetre = desktop.trouver_fenetre(terme, navigateurs_seulement=True, ecran=ecran)
        if fenetre is not None:
            return fenetre
    return None


def fenetre_montre_le_site(ctx: CommandContext, cle: str, fenetre) -> bool:
    """
    Cette fenetre affiche-t-elle bien le site vise ?

    Garde-fou indispensable : taper une requete, c est ecrire dans une page
    et appuyer sur Entree. Se tromper de fenetre, ce serait ecrire dans la
    recherche d un tout autre site -- ou pire, dans un formulaire. On verifie
    donc l adresse, et a defaut le titre, avant la moindre frappe.
    """
    from core import browser_tabs

    if fenetre is None:
        return False
    entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
    termes = [text_utils.normalize(t).strip()
              for t in termes_de_recherche(cle, entree)]
    termes = [t for t in termes if t]
    if not termes:
        return False

    adresse = text_utils.normalize(browser_tabs.adresse_courante(fenetre))
    if adresse:
        return any(terme in adresse for terme in termes)
    # Barre d adresse illisible : le titre de la fenetre reflete l onglet actif.
    titre = text_utils.normalize(fenetre.titre or "")
    return any(terme in titre for terme in termes)


def chercher_sur_le_site(ctx: CommandContext, cle: str, url: str, requete: str) -> bool:
    """
    Cherche sur un site, par SA barre de recherche quand c est possible.

    Fabriquer une adresse de recherche ne marche que sur les sites qui en ont
    une, stable, et qui n attendent rien d autre : Disney+ n en a pas, sa page
    de resultats ne porte pas la requete. Taper dans le champ du site marche
    partout ou il y en a un, et rend l adresse exacte que le site aurait
    produite lui-meme.

    Deux situations, pour ne pas charger une page pour rien :

      - le site est DEJA ouvert : on l amene devant et on tape dans son champ.
        Rien n est recharge, ce qui preserve une video en cours ;
      - il ne l est pas : l adresse de recherche va droit au but. On n ouvre
        l accueil pour y taper que si le site n a pas d adresse de recherche.

    L adresse configuree reste le repli general.
    """
    from urllib.parse import quote_plus

    from commands.interaction import fenetre_visee
    from core import recherche_page

    ctx.assistant.memoriser("site", cle)
    entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
    modele = entree.get("search_url") if isinstance(entree, dict) else None

    deja_ouvert = fenetre_du_site(ctx, cle) is not None
    if deja_ouvert or not modele:
        ok, _mode = afficher_site(ctx.config, cle, url, naviguer=False,
                                  assistant=ctx.assistant)
        if ok:
            fenetre = fenetre_visee(ctx)
            if (fenetre_montre_le_site(ctx, cle, fenetre)
                    and recherche_page.chercher(fenetre, requete)):
                return True

    if not modele:
        return False
    ok, _mode = afficher_site(ctx.config, cle,
                              modele.replace("{q}", quote_plus(requete)),
                              naviguer=True, assistant=ctx.assistant)
    return ok


def _site_connu(ctx: CommandContext) -> bool:
    """Guard : cible connue, et non reservee a une commande specialisee."""
    resolu = resolve_website(ctx.config, ctx.group("site"))
    return resolu is not None and resolu[0] not in SITES_RESERVES


@command(
    name="site_search",
    patterns=[
        # « va sur Netflix et mets Fast and Furious »
        r"^(?:va|vas|aller|ouvre|ouvrir|lance|lancer|passe|go|switch)\s+"
        r"(?:sur|a|dans|vers|to)?\s*"
        r"(?P<site>.+?)\s+(?:et|puis|pour|and|then)\s+" + VERBES_CONTENU + r"\s+(?P<query>.+)$",
        # « mets Fast and Furious sur Netflix », « play Fast and Furious on Netflix »
        r"^" + VERBES_CONTENU + r"\s+(?P<query>.+)\s+(?:sur|on)\s+(?P<site>[\w\s+]+)$",
        # « sur Netflix, mets Fast and Furious », « on Netflix, play X »
        r"^(?:sur|on)\s+(?P<site>.+?)\s*,?\s+" + VERBES_CONTENU + r"\s+(?P<query>.+)$",
    ],
    category="Sites web",
    description="Ouvrir un site et y lancer une recherche",
    examples=["va sur Netflix et mets Fast and Furious", "mets lofi hip hop sur YouTube",
              "play Fast and Furious on Netflix"],
    priority=97,
    guard=_site_connu,
)
def site_search(ctx: CommandContext) -> Response:
    """
    Affiche le site -- en reutilisant l onglet s il est deja ouvert -- puis y
    lance la recherche demandee.
    """
    resolu = resolve_website(ctx.config, ctx.group("site"))
    if resolu is None:
        return ctx.erreur("Je ne connais pas ce site.", "I don't know that site.")
    cle, url = resolu
    requete = ctx.group("query").strip()
    if not requete:
        return ctx.erreur("Que dois-je chercher sur " + cle + " ?",
                          "What should I look up on " + cle + "?")
    if chercher_sur_le_site(ctx, cle, url, requete):
        return ctx.reponse("Je cherche « " + requete + " » sur " + cle + ".",
                           "Searching " + cle + " for \"" + requete + "\".")
    return ctx.erreur("Je n'ai pas réussi à chercher sur " + cle + ".",
                      "I couldn't search on " + cle + ".")


def _site_en_contexte(ctx: CommandContext) -> bool:
    """Guard : un site a-t-il ete ouvert recemment ?"""
    return bool(ctx.assistant.rappeler("site"))


@command(
    name="site_search_contextuel",
    patterns=[
        r"^(?:cherche|chercher|recherche|rechercher|trouve|trouver|met[s]?|joue|jouer|"
        r"lance|lancer|regarde|regarder|affiche|montre|"
        r"search|find|play|watch|show)\s+(?:moi\s+|for\s+)?(.+)$",
    ],
    category="Sites web",
    description="Poursuivre sur le site en cours (« va sur YouTube » puis « recherche Damso »)",
    examples=["recherche Damso", "search Damso"],
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
    cle = ctx.assistant.rappeler("site")
    requete = ctx.arg.strip()
    if not cle or not requete:
        return ctx.erreur("Que dois-je chercher ?", "What should I search for?")
    entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
    url = entree.get("url") if isinstance(entree, dict) else str(entree)
    if chercher_sur_le_site(ctx, cle, url or "", requete):
        return ctx.reponse("Je cherche « " + requete + " » sur " + cle + ".",
                           "Searching " + cle + " for \"" + requete + "\".")
    return ctx.erreur("Je n'ai pas réussi à chercher sur " + cle + ".",
                      "I couldn't search on " + cle + ".")


def _site_pour_nouvel_onglet(ctx: CommandContext) -> bool:
    """Guard : « ouvre un nouvel onglet » sans site reste un onglet vide."""
    return resolve_website(ctx.config, ctx.arg) is not None


@command(
    name="ouvrir_site_nouvel_onglet",
    patterns=[
        r"^(?:ouvre|ouvrir|lance|lancer)\s+(?:moi\s+)?(?:un\s+|dans\s+un\s+)?"
        r"nouvel?\s+onglet\s+(.+)$",
        r"^(?:ouvre|ouvrir)\s+(.+?)\s+dans\s+un\s+nouvel?\s+onglet$",
        r"^open\s+(.+?)\s+in\s+a\s+new\s+tab$",
        r"^open\s+(?:a\s+)?new\s+tab\s+(.+)$",
    ],
    category="Sites web",
    description="Ouvrir un site dans un nouvel onglet",
    examples=["ouvre un nouvel onglet YouTube", "open YouTube in a new tab"],
    priority=98,
    guard=_site_pour_nouvel_onglet,
)
def ouvrir_site_nouvel_onglet(ctx: CommandContext) -> Response:
    """
    Force un NOUVEL onglet, meme si le site est deja ouvert ailleurs.

    C est la difference avec « ouvre X » et « va sur X », qui reprennent
    l onglet existant plutot que d en empiler un de plus. Meme regle d ecran
    que les autres ouvertures : dans le navigateur de l ecran de travail, ou
    une fenetre neuve la -- jamais dans celui d un autre ecran (voir
    `_nouvel_onglet`, qui a la charge de cela).
    """
    resolu = resolve_website(ctx.config, ctx.arg)
    if resolu is None:
        return ctx.erreur("Je ne connais pas ce site.", "I don't know that site.")
    cle, url = resolu
    ctx.assistant.memoriser("site", cle)
    if _nouvel_onglet(ctx, url):
        return ctx.reponse("Nouvel onglet sur " + cle + ".",
                           "New tab on " + cle + ".", speak=False)
    return ctx.erreur("Je n'ai pas réussi à ouvrir " + cle + ".",
                      "I couldn't open " + cle + ".")


# --------------------------------------------------------------------------
# Retour a l accueil
# --------------------------------------------------------------------------
# Tout titre de fenetre se termine par le nom du navigateur. Sans le retirer,
# « Sans titre - Google Chrome » passerait pour une page Google.
NAVIGATEURS_DANS_LE_TITRE = (
    "google chrome", "mozilla firefox", "microsoft edge", "brave browser",
    "chromium", "firefox", "brave", "opera", "vivaldi", "librewolf", "edge",
)


def sans_le_navigateur(titre: str) -> str:
    """Le titre d une fenetre, prive du nom du navigateur qui le termine."""
    norme = text_utils.normalize(titre or "").strip()
    for nom in NAVIGATEURS_DANS_LE_TITRE:
        if norme.endswith(nom):
            return norme[: -len(nom)].strip(" -|:")
    return norme


def site_du_titre(config, titre: str):
    """
    Le site reconnu dans un titre de fenetre. Retourne (cle, url) ou None.

    Repli pour les cas ou la barre d adresse est illisible : « Netflix -
    Google Chrome » suffit a savoir ou l on est.
    """
    jetons = set(text_utils.tokenize(sans_le_navigateur(titre)))
    if not jetons:
        return None
    for cle, entree in (config.get("websites", {}) or {}).items():
        url = entree.get("url") if isinstance(entree, dict) else str(entree)
        if not url:
            continue
        for terme in termes_de_recherche(cle, entree):
            if text_utils.normalize(terme).strip() in jetons:
                return cle, url
    return None


@command(
    name="retour_accueil",
    patterns=[
        r"^(?:retourne|retour|reviens|revenir|va|vas|aller|ramene\s+moi|"
        r"remonte|remonter|repasse)\s+(?:a\s+|sur\s+|vers\s+|au\s+)?"
        r"(?:la\s+|le\s+|l\s+)?(?:page\s+d\s+|ecran\s+d\s+)?"
        r"(?:accueil|home)(?:\s+(?:de\s+|du\s+|d\s+|sur\s+)?"
        r"(?:la\s+|le\s+|l\s+)?(?P<site>.+))?$",
        r"^(?:page\s+d\s+|ecran\s+d\s+)?(?:accueil|home)"
        r"(?:\s+(?:de\s+|du\s+|d\s+)?(?P<site>.+))?$",
        r"^(?:retourne|retour|reviens|revenir)\s+(?:a\s+)?(?:la\s+)?"
        r"page\s+(?:principale|d\s+accueil)$",
        # « go home », « go back to the home page of Netflix », « home page »
        r"^(?:go\s+(?:back\s+)?(?:to\s+)?)?(?:the\s+)?home(?:\s+page)?"
        r"(?:\s+(?:of|for)\s+(?P<site>.+))?$",
    ],
    keywords=[["retour", "accueil"], ["reviens", "accueil"], ["page", "accueil"],
              ["home", "page"]],
    category="Sites web",
    description="Revenir à la page d'accueil du site",
    examples=["retourne à l'accueil", "reviens à l'accueil de Netflix", "go home"],
    priority=94,
)
def retour_accueil(ctx: CommandContext) -> Response:
    """
    Ramene a la racine du site affiche, ou d un site nomme.

    Sans nom de site, on lit la barre d adresse du navigateur : cela marche
    pour n importe quel site, y compris ceux qui ne figurent pas dans la
    configuration. Le titre de la fenetre sert de repli.
    """
    from commands.interaction import fenetre_visee
    from core import browser_tabs, desktop

    demande = (ctx.group("site") or "").strip()
    if demande:
        trouve = resolve_website(ctx.config, demande)
        if trouve is None:
            return ctx.erreur("Je ne connais pas le site « " + demande + " ».",
                              "I don't know the site \"" + demande + "\".")
        cle, url = trouve
        ok, _comment = afficher_site(ctx.config, cle, url, naviguer=True,
                                     assistant=ctx.assistant)
        if ok:
            ctx.assistant.memoriser("site", cle)
            return ctx.reponse("Accueil de " + demande + ".",
                               demande + " home page.")
        return ctx.erreur("Je n'ai pas pu ouvrir l'accueil de " + demande + ".",
                          "I couldn't open the " + demande + " home page.")

    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return ctx.erreur("Je ne vois aucune page ouverte.",
                          "I don't see any open page.")

    accueil = browser_tabs.racine_du_site(browser_tabs.adresse_courante(fenetre))
    nom = accueil.split("//")[-1].strip("/") if accueil else ""
    if not accueil:
        # Barre d adresse illisible : on reconnait le site a son titre.
        trouve = site_du_titre(ctx.config, fenetre.titre)
        if trouve is None:
            return ctx.erreur(
                "Je n'arrive pas à savoir sur quel site vous êtes. "
                "Dites par exemple « retourne à l'accueil de Netflix ».",
                "I can't tell which site you're on. "
                "Say for example \"go back to the Netflix home page\".",
            )
        nom, accueil = trouve

    if desktop.naviguer_dans_fenetre(fenetre, accueil):
        return ctx.reponse("Retour à l'accueil de " + nom + ".",
                           "Back to the " + nom + " home page.")
    return ctx.erreur("Je n'ai pas pu revenir à l'accueil de " + nom + ".",
                      "I couldn't get back to the " + nom + " home page.")


# --------------------------------------------------------------------------
# « mets la serie The Flash » : rechercher, ouvrir la fiche, s arreter la
# --------------------------------------------------------------------------
# Ce qu on demande a un service de streaming tient en trois gestes : chercher,
# choisir le bon resultat, ouvrir sa fiche. La lecture elle-meme reste au
# doigt de l utilisateur -- c est l ecran ou l on appuie sur « Lecture » qui
# est vise, pas le film lance a son insu.
NATURES = (r"(?:serie|series|film|films|saison|episode|episodes|documentaire|"
           r"anime|animes|dessin\s+anime|emission|spectacle|match|programme|"
           r"show|shows|movie|movies|season|documentary|cartoon)")

VERBES_LANCER = (r"(?:met[s]?|mettre|lance|lancer|joue|jouer|regarde|regarder|"
                 r"ouvre|ouvrir|trouve|trouver|cherche|chercher|affiche|afficher|"
                 r"play|watch|find|search|open|put\s+on)")

# Ce qui prouve qu on est arrive sur la fiche d un titre.
MOTS_LECTURE = ("lecture", "play", "lire", "reprendre", "regarder maintenant",
                "bande-annonce", "bande annonce", "episodes", "saison",
                "watch now", "resume", "trailer", "season")

ATTENTE_RESULTATS = 12.0     # les catalogues sont lents a repondre
ATTENTE_FICHE = 6.0
TENTATIVES_CLIC = 2
STABILISATION = 1.5

# Un resultat de catalogue est une affiche. En dessous de cette taille, c est
# un fragment de texte -- souvent celui du message « nous n avons pas ce
# titre, mais voici autre chose », qu il ne faut surtout pas prendre pour un
# resultat.
TAILLE_VIGNETTE = 56

# Ce a quoi ressemble l adresse d un lecteur : le service a lance la lecture
# de lui-meme au lieu d ouvrir la fiche.
ADRESSES_LECTURE = ("/watch", "/play/", "/video/", "/lecture")
PAS_DE_SONDAGE = 0.8


def _site_courant(ctx: CommandContext):
    """
    Le service sur lequel on travaille. Retourne (cle, url) ou None.

    D abord celui dont on vient de parler, puis celui affiche sur l ecran de
    travail -- reconnu par son adresse, sinon par le titre de sa fenetre.
    """
    from commands.interaction import fenetre_visee
    from core import browser_tabs

    cle = ctx.assistant.rappeler("site")
    sites = ctx.config.get("websites", {}) or {}
    if cle and cle in sites:
        entree = sites[cle]
        url = entree.get("url") if isinstance(entree, dict) else str(entree)
        if url:
            return cle, url

    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return None
    hote = browser_tabs.racine_du_site(browser_tabs.adresse_courante(fenetre))
    if hote:
        jetons = set(text_utils.tokenize(text_utils.normalize(hote)))
        for cle, entree in sites.items():
            url = entree.get("url") if isinstance(entree, dict) else str(entree)
            if not url:
                continue
            for terme in termes_de_recherche(cle, entree):
                if text_utils.normalize(terme).strip() in jetons:
                    return cle, url
    return site_du_titre(ctx.config, fenetre.titre)


def _attendre(fenetre, predicat, delai: float, taille_min: int = 12):
    """Sonde la page jusqu a ce que `predicat` reponde, ou que le delai expire."""
    import time

    from core import interaction

    fin = time.time() + delai
    while True:
        trouve = predicat(interaction.elements_cliquables(fenetre, taille_min=taille_min))
        if trouve:
            return trouve
        if time.time() >= fin:
            return None
        time.sleep(PAS_DE_SONDAGE)


# Ce qui suit la nature n est pas toujours un titre : « mets le film PLUS
# FORT » est un reglage de volume, « mets la serie EN PAUSE » une commande de
# lecture. Ces phrases appartiennent a d autres commandes, qui les traitent
# mieux ; on leur rend la main.
FAUX_TITRES = (
    "plus fort", "moins fort", "en pause", "sur pause", "en marche",
    "en lecture", "en route", "en sourdine", "en silence", "en avant",
    "en arriere", "au debut", "a la fin", "plus vite", "moins vite",
    "en plein ecran", "en boucle",
)


def _est_un_titre(ctx: CommandContext) -> bool:
    """Garde : ce qui suit doit ressembler a un titre, pas a un ordre."""
    titre = text_utils.normalize(_titre_propre(ctx.group("titre"))).strip()
    return bool(titre) and titre not in FAUX_TITRES


def _titre_propre(titre: str) -> str:
    """
    Retire l article qui relie la nature au titre.

    « mets un episode DE Friends » : le titre cherche est « Friends », pas
    « de Friends », qui ne ressortirait dans aucun catalogue.
    """
    titre = (titre or "").strip()
    for liaison in ("de ", "du ", "des ", "d ", "d'"):
        if titre.lower().startswith(liaison):
            return titre[len(liaison):].strip()
    return titre


def _ouvrir_le_resultat(fenetre, titre):
    """
    Clique le bon resultat et attend d etre sur sa fiche.

    Retourne (cible, nom) ; `nom` vaut None si la fiche ne s est pas ouverte.

    Deux precautions, apprises en observant les catalogues. Le resultat
    apparait avant que la page ne soit prete a l ouvrir : on laisse donc
    passer un instant, et l element est RETROUVE juste avant chaque essai,
    car une page qui se construit encore remplace ses noeuds sous nos pieds.
    """
    import time

    from core import interaction

    cible = None
    for tentative in range(TENTATIVES_CLIC):
        cible = _attendre(
            fenetre,
            lambda cibles: interaction.chercher_cible(cibles, titre),
            ATTENTE_RESULTATS if tentative == 0 else 2.0,
            taille_min=TAILLE_VIGNETTE,
        )
        if cible is None:
            return None, None
        if tentative == 0:
            time.sleep(STABILISATION)
            # La grille a pu se reorganiser entre-temps.
            cible = interaction.chercher_cible(
                interaction.elements_cliquables(fenetre, taille_min=TAILLE_VIGNETTE),
                titre) or cible
        interaction.cliquer(cible)
        if _attendre(fenetre, _fiche_ouverte, ATTENTE_FICHE):
            return cible, interaction.titre_affiche(cible.nom)[:60]
        time.sleep(1.0)
    return cible, None


def _fiche_ouverte(cibles) -> bool:
    """La page propose-t-elle de lancer la lecture ?"""
    for cible in cibles:
        nom = text_utils.normalize(cible.nom).strip()
        if any(mot in nom for mot in MOTS_LECTURE):
            return True
    return False


@command(
    name="lancer_titre",
    patterns=[
        r"^" + VERBES_LANCER + r"\s+(?:moi\s+)?"
        r"(?:la\s+|le\s+|l\s+|les\s+|un\s+|une\s+|des\s+|the\s+|a\s+)?"
        + NATURES
        + r"\s+(?P<titre>.+?)(?:\s+(?:sur|on)\s+(?P<site>[\w\s+.-]+))?$",
    ],
    keywords=[["mets", "serie"], ["mets", "film"], ["lance", "serie"], ["lance", "film"],
              ["play", "movie"], ["watch", "show"]],
    category="Sites web",
    description="Chercher un film ou une série et ouvrir sa fiche",
    examples=["mets la série The Flash", "lance le film Interstellar sur Netflix",
              "watch the show The Flash", "play the movie Interstellar on Netflix"],
    priority=98,
    guard=_est_un_titre,
)
def lancer_titre(ctx: CommandContext) -> Response:
    """
    Fait toute la demarche : recherche, choix du bon resultat, ouverture de
    la fiche. On s arrete devant le bouton « Lecture » -- lancer le film est
    une decision qui revient a l utilisateur.
    """
    from commands.interaction import fenetre_visee
    from core import interaction

    titre = _titre_propre(ctx.group("titre"))
    dit_site = (ctx.group("site") or "").strip()
    resolu = resolve_website(ctx.config, dit_site) if dit_site else None
    if dit_site and resolu is None:
        # « sur » faisait partie du titre : « Le Pont sur la riviere Kwai ».
        titre = (titre + " sur " + dit_site).strip()
    if not titre:
        return ctx.erreur("Quel titre dois-je chercher ?",
                          "Which title should I look for?")

    if resolu is None:
        resolu = _site_courant(ctx)
    if resolu is None:
        return ctx.erreur(
            "Sur quel service ? Dites par exemple « mets la série "
            + titre + " sur Netflix ».",
            "On which service? Say for example \"put on the series "
            + titre + " on Netflix\".",
        )
    cle, url = resolu
    if not chercher_sur_le_site(ctx, cle, url, titre):
        return ctx.erreur("Je n'ai pas réussi à chercher sur " + cle + ".",
                          "I couldn't search on " + cle + ".")

    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return ctx.erreur("Je ne vois plus la fenêtre de " + cle + ".",
                          "I can't see the " + cle + " window any more.")

    resultat, nom = _ouvrir_le_resultat(fenetre, titre)
    if resultat is None:
        return ctx.erreur(
            "Je ne trouve pas « " + titre + " » sur " + cle + ".",
            "I can't find \"" + titre + "\" on " + cle + ".",
        )
    if nom is not None:
        # Certains services ouvrent la fiche, d autres reprennent la lecture
        # d un seul clic. On dit ce qui s est reellement passe.
        from core import browser_tabs

        adresse = browser_tabs.adresse_courante(fenetre).lower()
        if any(marque in adresse for marque in ADRESSES_LECTURE):
            return ctx.reponse("Je lance " + nom + ".", "Playing " + nom + ".")
        return ctx.reponse(nom + " est ouvert.", nom + " is open.")
    nom = interaction.titre_affiche(resultat.nom)[:60]
    # Le resultat a ete clique mais rien ne propose de le lire : c est souvent
    # que le catalogue ne l a pas et que la page suggere autre chose.
    return ctx.erreur(
        "J'ai ouvert « " + nom + " » sur " + cle
        + ", mais je n'y vois pas de bouton de lecture. "
        "Le titre n'est peut-être pas disponible sur ce service.",
        "I opened \"" + nom + "\" on " + cle
        + ", but I don't see a play button there. "
        "The title may not be available on this service.",
    )
