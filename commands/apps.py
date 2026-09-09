"""
Ouverture et fermeture d applications Windows.

La table nom parle -> executable vit dans config.yaml (section
`applications`), ce qui permet d en ajouter sans toucher au code.
"""

from __future__ import annotations

import logging

from core import text_utils, win_utils
from core.context import CommandContext, Response
from core.registry import command

log = logging.getLogger(__name__)

# Mots parasites fréquents devant un nom d application.
_FILLERS = (
    "moi", "le", "la", "les", "l", "un", "une", "des", "mon", "ma", "mes",
    "the", "my", "app", "appli", "applis", "application", "applications",
    "logiciel", "logiciels", "programme", "software", "stp",
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


def alias_exacts(entrees) -> set:
    """Tous les noms sous lesquels ces entrees se laissent appeler."""
    noms = set()
    for cle, entree in (entrees or {}).items():
        noms.add(text_utils.normalize(cle).strip())
        alias = entree.get("aliases", []) if isinstance(entree, dict) else []
        for nom in alias or ():
            noms.add(text_utils.normalize(str(nom)).strip())
    return {n for n in noms if n}


def _is_known_app(ctx: CommandContext) -> bool:
    """
    Guard : la cible est-elle une application connue ?

    Nuance : un nom qui designe EXACTEMENT un site connu lui revient, meme
    s il ressemble au nom d une application. « ouvre Google » veut la page
    Google, pas le navigateur qui porte son nom -- alors que « ouvre Chrome »,
    lui, nomme bien l application.
    """
    if resolve_app(ctx.config, ctx.arg) is None:
        return False
    cible = clean_target(ctx.arg)
    if cible in alias_exacts(ctx.config.get("applications", {})):
        return True
    return cible not in alias_exacts(ctx.config.get("websites", {}))


# Une application ouverte sans precision va sur l ecran principal : c est la
# ou l on travaille, l autre servant souvent a autre chose.
ECRAN_PAR_DEFAUT = 1


# Mots qui relient le nom de l application a la mention d ecran, et qui ne
# font donc partie ni de l un ni de l autre.
LIAISONS_ECRAN = ("sur", "dans", "a", "vers", "l", "le", "la", "du", "de", "des")


def separer_ecran(demande: str) -> tuple:
    """
    Detache la mention d ecran du nom d application.

    Retourne (nom, numero d ecran ou None). Le numero se lit comme partout
    ailleurs : chiffre, ordinal, « de droite », et meme « de » tout court,
    que la reconnaissance vocale rend a la place de « deux ».
    """
    from commands.media import MOTS_ECRAN
    from core import deduction, desktop

    mots = text_utils.tokenize(text_utils.normalize(demande or ""))
    position = next((i for i, mot in enumerate(mots) if mot in MOTS_ECRAN), None)
    if position is None or position == 0:
        return (demande or "").strip(), None

    apres = mots[position + 1:position + 3]
    avant = mots[max(0, position - 2):position]

    numero, mot_du_numero = None, None
    if any(mot in ("droite", "droit") for mot in apres):
        numero = len(desktop.ecrans()) or None
    elif "gauche" in apres or "principal" in apres:
        numero = 1
    else:
        # Apres « ecran » d abord, puis juste avant : « le deuxieme ecran ».
        for candidat in list(apres) + list(reversed(avant)):
            numero = deduction.nombre_entendu(candidat)
            if numero is not None:
                mot_du_numero = candidat
                break
    if numero is None:
        return (demande or "").strip(), None

    # Tout ce qui introduit la mention d ecran appartient a la mention, pas
    # au nom de l application : « Paint sur le deuxieme ecran » -> « Paint ».
    coupe = position
    while coupe > 0 and (mots[coupe - 1] in LIAISONS_ECRAN
                         or mots[coupe - 1] == mot_du_numero):
        coupe -= 1
    if coupe == 0:
        return "", numero

    # On revient au texte d origine pour garder accents et majuscules.
    norme = text_utils.normalize(demande)
    curseur, fin = 0, 0
    for i, mot in enumerate(mots[:coupe]):
        curseur = norme.find(mot, curseur)
        if curseur < 0:
            break
        curseur += len(mot)
        fin = curseur
    return demande[:fin].strip(), numero


# Le mot qui precede le nom leve l ambiguite, et il n a donc rien d un
# parasite : beaucoup de choses portent le meme nom des deux cotes -- Claude,
# Spotify, Discord existent en application ET en site.
MOTS_APPLICATION = ("application", "applications", "appli", "applis", "app",
                    "logiciel", "programme", "software")
MOTS_SITE = ("site", "page", "web")


def nature_demandee(demande: str) -> str:
    """
    « application », « site » : ce que la phrase precise elle-meme.

    Retourne "app", "site", ou "" quand rien ne tranche.
    """
    jetons = set(text_utils.tokenize(text_utils.normalize(demande or "")))
    if jetons.intersection(MOTS_APPLICATION):
        return "app"
    if jetons.intersection(MOTS_SITE):
        return "site"
    return ""


def _est_une_application(ctx: CommandContext) -> bool:
    """
    Guard : la phrase designe-t-elle une application ?

    D abord ce que la phrase DIT : « ouvre l application Claude » demande le
    logiciel, « ouvre le site Claude » la page. Sans precision, trois cas : un
    nom qui figure tel quel dans la configuration des applications en est une ;
    un nom qui figure tel quel dans celle des SITES n en est pas une -- « ouvre
    Google » veut la page, pas le navigateur qui porte son nom ; sinon, on
    regarde ce qui est reellement installe.
    """
    from core import applications

    nom, _ecran = separer_ecran(ctx.arg)
    cible = clean_target(nom)
    if not cible:
        return False

    nature = nature_demandee(nom)
    if nature == "site":
        return False
    if nature == "app":
        return (resolve_app(ctx.config, cible) is not None
                or applications.chercher(cible) is not None)

    if cible in alias_exacts(ctx.config.get("applications", {})):
        return True
    if cible in alias_exacts(ctx.config.get("websites", {})):
        return False
    if resolve_app(ctx.config, nom) is not None:
        return True
    return applications.chercher(cible) is not None


def _placer(connues: set, index: int, processus: str = "") -> bool:
    """
    Attend que la fenetre apparaisse et l amene sur l ecran demande.

    `processus` vient de la configuration quand elle le precise : c est le
    seul moyen sur de reconnaitre l application parmi les fenetres qui
    s ouvrent en meme temps.
    """
    from core import desktop

    fenetre = desktop.attendre_nouvelle_fenetre(connues, processus=processus)
    if fenetre is None:
        return False
    if fenetre.ecran == index:
        return True
    return desktop.deplacer_vers_ecran(fenetre.handle, index)


def _joli(libelle: str) -> str:
    """« bloc note » se dit « Bloc note » quand on l annonce."""
    libelle = (libelle or "").strip()
    return libelle[:1].upper() + libelle[1:] if libelle else libelle


@command(
    name="open_app",
    patterns=[r"^" + OPEN_VERBS + r"\s+(.+)$"],
    category="Applications",
    description="Ouvrir une application, au besoin sur un écran précis",
    examples=["ouvre Chrome", "lance la calculatrice",
              "ouvre Visual Studio Code sur l'écran 1"],
    priority=60,
    guard=_est_une_application,
)
def open_app(ctx: CommandContext) -> Response:
    """
    Ouvre une application, declaree ou simplement installee.

    La configuration reste prioritaire -- elle donne les chemins exacts --
    puis on cherche dans ce qui est installe sur la machine. La fenetre est
    amenee sur l ecran demande, ou sur l ecran principal par defaut.
    """
    from core import applications, desktop

    nom, ecran = separer_ecran(ctx.arg)
    if not nom:
        return Response.error("Quelle application dois-je ouvrir ?")
    ecrans = desktop.ecrans()
    if ecran is not None and ecrans and ecran > len(ecrans):
        return Response.error(
            "Je ne vois que " + str(len(ecrans)) + " écran(s), pas d'écran " + str(ecran) + "."
        )
    index = ecran or ECRAN_PAR_DEFAUT
    connues = desktop.poignees_visibles()

    # Le nom, debarrasse de « l application » et autres mots de nature.
    cible_nom = clean_target(nom) or nom
    explicite = nature_demandee(nom) == "app"

    resolu = resolve_app(ctx.config, cible_nom)
    if resolu is not None and (explicite or _prefere_lapplication(ctx.config, nom)):
        cle, entree = resolu
        libelle = (entree.get("aliases") or [cle])[0]
        ok, detail = win_utils.launch(entree.get("paths", []) or [])
        if ok:
            _placer(connues, index, processus=str(entree.get("process", "") or ""))
            return Response(text="J'ouvre " + _joli(libelle) + _sur(ecran) + ".")
        # Le chemin configure est faux : l application est peut-etre installee
        # ailleurs, on continue plutot que d abandonner.
        log.debug("Chemin configure inutilisable pour %s : %s", cle, detail)

    trouvee = applications.chercher(cible_nom)
    if trouvee is None:
        return Response.error(
            "Je ne trouve pas d'application « " + cible_nom + " » sur cet ordinateur."
        )
    libelle, cible = trouvee
    ok, detail = applications.lancer(cible)
    if not ok:
        return Response.error("Impossible d'ouvrir " + libelle + ". " + detail)
    _placer(connues, index)
    return Response(text="J'ouvre " + _joli(libelle) + _sur(ecran) + ".")


def _sur(ecran) -> str:
    return (" sur l'écran " + str(ecran)) if ecran else ""


def _prefere_lapplication(config, nom: str) -> bool:
    """La configuration l emporte, sauf si le nom designe exactement un site."""
    cible = clean_target(nom)
    if cible in alias_exacts(config.get("applications", {})):
        return True
    return cible not in alias_exacts(config.get("websites", {}))


VERBES_ALLER = (r"(?:va|vas|aller|bascule|basculer|passe|passer|affiche|afficher|"
                r"montre|montrer|retourne|retourner|reviens|revenir)")


def _fenetre_de_lapplication(nom: str, config):
    """
    Une fenetre ouverte qui corresponde a ce nom, ou None.

    On regarde le PROCESSUS d abord -- « chrome » et « chrome.exe » se
    reconnaissent sans ambiguite -- puis le titre, qui rattrape les logiciels
    dont l executable ne porte pas leur nom : Visual Studio Code s execute
    sous « Code.exe ».
    """
    from core import desktop, text_utils

    cible = text_utils.normalize(nom or "").strip()
    if not cible:
        return None

    processus_attendu = ""
    resolu = resolve_app(config, cible)
    if resolu is not None:
        processus_attendu = (resolu[1].get("process") or "").lower()

    par_titre = None
    for fenetre in desktop.fenetres():
        processus = (fenetre.processus or "").lower()
        if processus_attendu and processus == processus_attendu:
            return fenetre
        if cible in text_utils.normalize(processus.rsplit(".", 1)[0]):
            return fenetre
        # Le titre est un repli : il change au gre de ce qui est affiche, donc
        # on ne s en contente qu a defaut de mieux.
        if par_titre is None and cible in text_utils.normalize(fenetre.titre or ""):
            par_titre = fenetre
    return par_titre


@command(
    name="aller_sur_application",
    patterns=[r"^" + VERBES_ALLER + r"\s+(?:moi\s+)?(?:sur|a|vers|dans)?\s*"
              r"(?:l\s+|le\s+|la\s+|les\s+)?(.+)$"],
    category="Applications",
    description="Aller sur une application",
    examples=["va sur Chrome", "affiche Spotify"],
    # Sous open_app et open_website : « va sur YouTube » reste un site, « va
    # sur l ecran 2 » reste un ecran. Ne restent ici que les applications.
    priority=58,
    guard=_est_une_application,
)
def aller_sur_application(ctx: CommandContext) -> Response:
    """Amène une application au premier plan, ou l'ouvre si elle est fermée."""
    from core import desktop

    nom, _ecran = separer_ecran(ctx.arg)
    cible = clean_target(nom) or nom
    fenetre = _fenetre_de_lapplication(cible, ctx.config)
    if fenetre is None:
        # Pas ouverte : « va sur Chrome » veut voir Chrome, ouvrir revient au
        # meme pour qui parle.
        return open_app(ctx)
    if not desktop.mettre_au_premier_plan(fenetre.handle):
        return Response.error("Je n'arrive pas à afficher " + _joli(cible) + ".")
    return Response(text="Voilà " + _joli(cible) + ".", speak=False)


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
        return Response(text="J'ai fermé " + label + ".")
    return Response.error(label + " ne semble pas ouvert. (" + detail + ")")


@command(
    name="list_apps",
    informatif=True,
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
