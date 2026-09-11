"""
Fenetres, onglets et affichage : naviguer sans toucher au clavier.
"""

from __future__ import annotations

import re

from core import desktop, win_utils
from core.context import CommandContext, Response
from core.registry import command


def _raccourci(libelle: str, *touches) -> Response:
    if win_utils.raccourci(*touches):
        return Response(text=libelle, speak=False)
    return Response.error("Je n'ai pas pu envoyer ce raccourci.")


# --------------------------------------------------------------------------
# Fermer un onglet par son numéro d'ordre
# --------------------------------------------------------------------------
TYPE_BOUTON = 50000
MOTS_FERMER = ("ferm", "clos")


def _navigateur_vise(ctx: CommandContext, ecran_demande: int | None = None):
    """
    La fenêtre de navigateur à viser.

    L'ÉCRAN DE TRAVAIL passe avant le reste -- « ferme l'onglet 3 » vise le
    navigateur de l'écran où l'on travaille, comme tout le reste dans Alma,
    même s'il est minimisé et même si une autre fenêtre est devant. À défaut
    de navigateur sur cet écran, celui au premier plan, puis n'importe lequel.
    """
    navigateurs = [f for f in desktop.fenetres() if f.est_navigateur]
    if not navigateurs:
        return None

    courante = ctx.assistant.fenetre_courante()
    poignee = courante.handle if courante is not None else 0

    ecran = (ecran_demande if ecran_demande is not None
             else getattr(ctx.assistant, "ecran_actif", None))
    if ecran is not None:
        sur_ecran = [f for f in navigateurs if f.ecran == ecran]
        if sur_ecran:
            ici = [f for f in sur_ecran if f.handle == poignee]
            return (ici or sur_ecran)[0]

    partout = [f for f in navigateurs if f.handle == poignee]
    return (partout or navigateurs)[0]


def _onglets_gauche_a_droite(fenetre) -> list:
    """
    Les onglets, du plus à gauche (numéro 1) au plus à droite.

    On trie sur la position X plutôt que de se fier à l'ordre de l'arbre
    d'accessibilité : celui-ci suit d'ordinaire l'affichage, mais un tri
    explicite couvre les cas tordus (onglets épinglés, groupes).
    """
    from core import browser_tabs

    def gauche(onglet):
        try:
            return onglet.element.CurrentBoundingRectangle.left
        except Exception:
            return 10 ** 9

    return sorted(browser_tabs.onglets(fenetre), key=gauche)


def _fermer_onglet(onglet) -> bool:
    """
    Ferme cet onglet, sans le mettre au premier plan si possible.

    Chaque onglet expose un bouton « Fermer » : l'invoquer marche même
    fenêtre minimisée, et ne dérange pas l'onglet courant. Le repli --
    activer l'onglet puis Ctrl+W -- exige le premier plan.
    """
    from core import browser_tabs

    uia, module = browser_tabs._client()
    if module is not None:
        try:
            condition = uia.CreatePropertyCondition(
                module.UIA_ControlTypePropertyId, TYPE_BOUTON)
            boutons = onglet.element.FindAll(module.TreeScope_Descendants, condition)
            for index in range(boutons.Length):
                bouton = boutons.GetElement(index)
                if any(m in (bouton.CurrentName or "").lower() for m in MOTS_FERMER):
                    motif = bouton.GetCurrentPattern(module.UIA_InvokePatternId)
                    motif.QueryInterface(module.IUIAutomationInvokePattern).Invoke()
                    return True
        except Exception:
            pass

    if onglet.activer():
        desktop.mettre_au_premier_plan(onglet.fenetre.handle)
        return win_utils.raccourci("ctrl", "w")
    return False


@command(
    name="fermer_onglet_numero",
    patterns=[
        # « ferme l'onglet 3 », « ferme l'onglet numéro trois », « ferme onglet 2 »,
        # « ferme l'onglet 3 sur l'écran 2 »
        r"^(?:ferme|fermer|supprime|enleve|vire|degage)\s+(?:moi\s+)?"
        r"(?:l\s+|le\s+|la\s+)?onglet\s+(?:numero\s+|num\s+|no\s+|n\s+)?(?P<n>\S+?)"
        r"(?:\s+(?:sur\s+)?(?:l\s+)?ecran\s+(?P<ecran>\d+))?\s*$",
        # « ferme le troisième onglet », « ferme le 3e onglet »
        r"^(?:ferme|fermer|supprime|enleve|vire|degage)\s+(?:moi\s+)?"
        r"(?:l\s+|le\s+|la\s+)?(?P<n>\d+\s*e?|premier|premiere|deuxieme|second|seconde|"
        r"troisieme|quatrieme|cinquieme|sixieme|septieme|huitieme|neuvieme|dixieme|"
        r"dernier|derniere)\s+onglet"
        r"(?:\s+(?:sur\s+)?(?:l\s+)?ecran\s+(?P<ecran>\d+))?\s*$",
        # « close tab 3 », « close tab number 3 sur screen 2 »
        r"^(?:close|shut)\s+(?:down\s+)?tab\s+(?:number\s+|no\.?\s+|#\s*)?(?P<n>\S+?)"
        r"(?:\s+on\s+screen\s+(?P<ecran>\d+))?\s*$",
        # « close the third tab », « close the last tab »
        r"^close\s+(?:the\s+)?(?P<n>\d+(?:st|nd|rd|th)?|first|second|third|fourth|fifth|"
        r"sixth|seventh|eighth|ninth|tenth|last)\s+tab(?:\s+on\s+screen\s+(?P<ecran>\d+))?\s*$",
    ],
    category="Fenêtres",
    description="Fermer un onglet par son numéro (le plus à gauche est le 1)",
    examples=["ferme l'onglet 3", "ferme le deuxième onglet", "close tab 3"],
    # Pas de guard « un navigateur existe » : une demande NUMÉROTÉE n'a pas de
    # meilleur destinataire, et sans navigateur on préfère le dire clairement
    # plutôt que fermer l'onglet courant de la fenêtre au hasard.
    priority=95,
)
def fermer_onglet_numero(ctx: CommandContext) -> Response:
    """Ferme l'onglet dont on donne le rang, en comptant depuis la gauche."""
    from core import deduction, text_utils

    ecran = ctx.match.groupdict().get("ecran") if ctx.match else None
    fenetre = _navigateur_vise(ctx, int(ecran) if ecran else None)
    if fenetre is None:
        return Response.error("Je ne vois aucun navigateur ouvert.")
    onglets = _onglets_gauche_a_droite(fenetre)
    if not onglets:
        return Response.error("Je ne vois aucun onglet dans ce navigateur.")

    brut = text_utils.normalize(ctx.group("n") or "").strip()
    if brut in ("dernier", "derniere"):
        numero = len(onglets)
    else:
        brut = re.sub(r"^(\d+)\s*e$", r"\1", brut)      # « 3e » -> « 3 »
        numero = deduction.nombre_entendu(brut, maximum=max(9, len(onglets)))
    if numero is None:
        return Response.error("Quel onglet dois-je fermer ? Donnez son numéro.")
    if not 1 <= numero <= len(onglets):
        pluriel = "s" if len(onglets) > 1 else ""
        return Response.error(
            "Il n'y a que " + str(len(onglets)) + " onglet" + pluriel
            + " : pas d'onglet " + str(numero) + "."
        )

    if _fermer_onglet(onglets[numero - 1]):
        return Response(text="Onglet " + str(numero) + " fermé.", speak=False)
    return Response.error("Je n'ai pas réussi à fermer cet onglet.")


@command(
    name="nouvel_onglet",
    patterns=[r"(?:ouvre|nouveau|nouvel|cree)\s+(?:un\s+)?(?:nouvel\s+)?onglet$",
              r"^nouvel\s+onglet$",
              r"(?:open|create)\s+(?:a\s+)?new\s+tab$", r"^new\s+tab$"],
    keywords=[["nouvel", "onglet"], ["nouveau", "onglet"], ["new", "tab"]],
    category="Fenêtres",
    description="Ouvrir un nouvel onglet",
    examples=["ouvre un nouvel onglet", "new tab"],
    priority=93,
)
def nouvel_onglet(ctx: CommandContext) -> Response:
    return _raccourci("Nouvel onglet.", "ctrl", "t")


@command(
    name="fermer_onglet",
    patterns=[r"(?:ferme|fermer)\s+(?:cet?\s+|l\s+)?onglet$",
              r"^(?:ferme|fermer)\s+la\s+page$",
              r"^close\s+(?:this\s+|the\s+)?tab$", r"^close\s+(?:this\s+|the\s+)?page$"],
    keywords=[["ferme", "onglet"], ["close", "tab"]],
    category="Fenêtres",
    description="Fermer l'onglet courant",
    examples=["ferme cet onglet", "close this tab"],
    priority=93,
)
def fermer_onglet(ctx: CommandContext) -> Response:
    return _raccourci("Onglet fermé.", "ctrl", "w")


@command(
    name="rouvrir_onglet",
    patterns=[r"(?:rouvre|rouvrir|restaure|recupere)\s+(?:l\s+)?onglet",
              r"(?:onglet|page)\s+(?:ferme|precedente)\s+(?:par\s+erreur)?",
              r"(?:reopen|restore)\s+(?:the\s+)?(?:closed\s+|last\s+)?tab"],
    keywords=[["rouvre", "onglet"], ["reopen", "tab"]],
    category="Fenêtres",
    description="Rouvrir le dernier onglet fermé",
    examples=["rouvre l'onglet fermé", "reopen the closed tab"],
    priority=94,
)
def rouvrir_onglet(ctx: CommandContext) -> Response:
    return _raccourci("Onglet rouvert.", "ctrl", "shift", "t")


@command(
    name="onglet_suivant",
    patterns=[r"^onglet\s+suivant$", r"(?:passe|va)\s+a\s+l\s+onglet\s+suivant",
              r"^next\s+tab$"],
    keywords=[["onglet", "suivant"], ["next", "tab"]],
    category="Fenêtres",
    description="Passer à l'onglet suivant",
    examples=["onglet suivant", "next tab"],
    priority=95,
)
def onglet_suivant(ctx: CommandContext) -> Response:
    return _raccourci("Onglet suivant.", "ctrl", "tab")


@command(
    name="onglet_precedent",
    patterns=[r"^onglet\s+precedent$", r"(?:reviens|retourne)\s+a\s+l\s+onglet\s+precedent",
              r"^previous\s+tab$"],
    keywords=[["onglet", "precedent"], ["previous", "tab"]],
    category="Fenêtres",
    description="Revenir à l'onglet précédent",
    examples=["onglet précédent", "previous tab"],
    priority=95,
)
def onglet_precedent(ctx: CommandContext) -> Response:
    return _raccourci("Onglet précédent.", "ctrl", "shift", "tab")


@command(
    name="rafraichir",
    patterns=[r"^(?:rafraichis|rafraichir|actualise|actualiser|recharge|recharger)\s*(?:la\s+page)?$",
              r"^(?:refresh|reload)\s*(?:the\s+page)?$"],
    keywords=[["actualise"], ["recharge"], ["refresh"], ["reload"]],
    category="Fenêtres",
    description="Recharger la page",
    examples=["actualise la page", "refresh the page"],
    priority=90,
)
def rafraichir(ctx: CommandContext) -> Response:
    return _raccourci("Page rechargée.", "f5")


@command(
    name="page_precedente",
    patterns=[r"^(?:page|retour)\s+(?:precedente|arriere)$",
              r"^(?:reviens|retourne|reviens\s+en)\s+(?:a\s+la\s+page\s+precedente|arriere)$",
              r"^previous\s+page$", r"^(?:go\s+)?back\s+page$", r"^go\s+back$"],
    keywords=[["page", "precedente"], ["previous", "page"]],
    category="Fenêtres",
    description="Revenir à la page précédente",
    examples=["page précédente", "previous page"],
    priority=95,
)
def page_precedente(ctx: CommandContext) -> Response:
    return _raccourci("Page précédente.", "alt", "gauche")


@command(
    name="page_suivante",
    patterns=[r"^page\s+suivante$", r"^(?:avance|va)\s+a\s+la\s+page\s+suivante$",
              r"^next\s+page$", r"^go\s+forward$"],
    keywords=[["page", "suivante"], ["next", "page"]],
    category="Fenêtres",
    description="Aller à la page suivante",
    examples=["page suivante", "next page"],
    priority=95,
)
def page_suivante(ctx: CommandContext) -> Response:
    return _raccourci("Page suivante.", "alt", "droite")


@command(
    name="zoom_avant",
    patterns=[r"(?:zoom|agrandis|agrandir|grossis)\s*(?:avant|le\s+texte|la\s+page|plus)?$",
              r"(?:c\s+est\s+trop\s+petit|plus\s+gros)",
              r"^zoom\s+in$", r"^(?:make\s+it\s+bigger|too\s+small)$"],
    keywords=[["zoom", "avant"], ["agrandis", "texte"], ["zoom", "in"]],
    category="Fenêtres",
    description="Agrandir l'affichage",
    examples=["zoom avant", "zoom in"],
    priority=91,
)
def zoom_avant(ctx: CommandContext) -> Response:
    return _raccourci("Zoom avant.", "ctrl", "plus")


@command(
    name="zoom_arriere",
    patterns=[r"(?:dezoom|dezoome|reduis|rapetisse)\s*(?:la\s+page|le\s+texte)?$",
              r"zoom\s+arriere$", r"(?:c\s+est\s+trop\s+gros|plus\s+petit)",
              r"^zoom\s+out$", r"^(?:make\s+it\s+smaller|too\s+big)$"],
    keywords=[["zoom", "arriere"], ["reduis", "texte"], ["zoom", "out"]],
    category="Fenêtres",
    description="Réduire l'affichage",
    examples=["zoom arrière", "zoom out"],
    priority=91,
)
def zoom_arriere(ctx: CommandContext) -> Response:
    return _raccourci("Zoom arrière.", "ctrl", "moins")


@command(
    name="zoom_normal",
    patterns=[r"(?:remet[s]?|remettre|reinitialise)\s+(?:le\s+)?zoom",
              r"^zoom\s+(?:normal|par\s+defaut|cent\s+pour\s+cent)$",
              r"(?:taille|zoom)\s+normale?$",
              r"^reset\s+zoom$", r"^(?:normal|default)\s+zoom$"],
    keywords=[["zoom", "normal"], ["reset", "zoom"]],
    category="Fenêtres",
    description="Revenir au zoom normal",
    examples=["zoom normal", "reset zoom"],
    priority=93,
)
def zoom_normal(ctx: CommandContext) -> Response:
    return _raccourci("Zoom réinitialisé.", "ctrl", "zero")


@command(
    name="plein_ecran",
    patterns=[r"(?:met[s]?|passe|mettre)\s+(?:en\s+)?plein\s+ecran",
              r"^plein\s+ecran$", r"(?:quitte|sors\s+du)\s+plein\s+ecran",
              r"^(?:go\s+)?full\s*screen$", r"(?:exit|leave)\s+full\s*screen$"],
    keywords=[["plein", "ecran"], ["full", "screen"]],
    category="Fenêtres",
    description="Basculer en plein écran",
    examples=["plein écran", "full screen"],
    priority=96,
)
def plein_ecran(ctx: CommandContext) -> Response:
    return _raccourci("Plein écran.", "f11")


@command(
    name="minimiser",
    patterns=[r"(?:minimise|minimiser|reduis|reduire|cache)\s+(?:la\s+|cette\s+)?fenetre",
              r"^(?:minimise|reduis)$",
              r"^minimi[sz]e\s+(?:this\s+|the\s+)?window$", r"^minimi[sz]e$"],
    keywords=[["minimise", "fenetre"], ["minimize", "window"]],
    category="Fenêtres",
    description="Réduire la fenêtre active",
    examples=["minimise la fenêtre", "minimize the window"],
    priority=94,
)
def minimiser(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre réduite.", "win", "bas")


@command(
    name="agrandir_fenetre",
    patterns=[r"(?:agrandis|agrandir|maximise|maximiser)\s+(?:la\s+|cette\s+)?fenetre",
              r"^maximi[sz]e\s+(?:this\s+|the\s+)?window$", r"^maximi[sz]e$"],
    keywords=[["agrandis", "fenetre"], ["maximise"], ["maximize", "window"]],
    category="Fenêtres",
    description="Agrandir la fenêtre active",
    examples=["agrandis la fenêtre", "maximize the window"],
    priority=94,
)
def agrandir_fenetre(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre agrandie.", "win", "haut")


@command(
    name="fermer_fenetre",
    patterns=[r"(?:ferme|fermer)\s+(?:la\s+|cette\s+)?fenetre$",
              r"^close\s+(?:this\s+|the\s+)?window$"],
    keywords=[["ferme", "fenetre"], ["close", "window"]],
    category="Fenêtres",
    description="Fermer la fenêtre active",
    examples=["ferme la fenêtre", "close this window"],
    priority=94,
)
def fermer_fenetre(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre fermée.", "alt", "f4")


@command(
    name="changer_fenetre",
    patterns=[r"(?:change|changer|bascule|passe)\s+(?:de\s+|a\s+la\s+)?fenetre",
              r"^(?:fenetre\s+suivante|alt\s+tab)$",
              r"^(?:switch|change)\s+windows?$", r"^next\s+window$"],
    keywords=[["change", "fenetre"], ["switch", "window"]],
    category="Fenêtres",
    description="Passer à la fenêtre suivante",
    examples=["change de fenêtre", "switch window"],
    priority=94,
)
def changer_fenetre(ctx: CommandContext) -> Response:
    return _raccourci("Fenêtre suivante.", "alt", "tab")


@command(
    name="afficher_bureau",
    patterns=[r"(?:affiche|montre|va\s+sur|retourne\s+sur)\s+(?:le\s+)?bureau$",
              r"(?:reduis|minimise)\s+tout$",
              r"^(?:show|go\s+to)\s+(?:the\s+)?desktop$", r"^minimi[sz]e\s+(?:all|everything)$"],
    keywords=[["affiche", "bureau"], ["show", "desktop"]],
    category="Fenêtres",
    description="Afficher le bureau",
    examples=["affiche le bureau", "show desktop"],
    priority=96,
)
def afficher_bureau(ctx: CommandContext) -> Response:
    return _raccourci("Bureau affiché.", "win", "d")


@command(
    name="capture_zone",
    patterns=[r"(?:capture|capturer|prend[s]?)\s+(?:une\s+)?(?:zone|partie|selection|region)",
              r"capture\s+d\s+ecran\s+partielle",
              r"(?:capture|take|grab)\s+(?:a\s+)?(?:screen\s+)?(?:region|area|selection)"],
    keywords=[["capture", "zone"], ["capture", "region"]],
    category="Fenêtres",
    description="Capturer une zone de l'écran",
    examples=["capture une zone", "capture a region"],
    priority=96,
)
def capture_zone(ctx: CommandContext) -> Response:
    """Ouvre l'outil de capture de Windows pour sélectionner une région."""
    if win_utils.raccourci("win", "shift", "s"):
        return Response(text="Sélectionnez la zone à capturer.", speak=False)
    return Response.error("Je n'ai pas pu ouvrir l'outil de capture.")


# Ce qui, devant « sur l ecran N », n est qu une facon de s adresser a Alma et
# ne nomme donc rien : « va sur... », « mets-toi sur... ».
_TOURNURE = re.compile(
    r"^(?:va|vas|aller|passe|passer|bascule|basculer|travaille|reste|rester|"
    r"met[s]?\s+toi|place\s+toi|concentre\s+toi|utilise|prends|affiche|montre|"
    r"pour|sur|dans|vers|"
    r"go|switch|move|use|show|display|work\s+on|for|on|in|to)\s*(?:moi\s+)?"
    r"(?:sur|a|vers|dans|to)?\s*"
    r"(?:l\s+|le\s+|la\s+|les\s+|the\s+)?"
)


def _seulement_l_ecran(ctx: CommandContext) -> bool:
    """
    Guard : la phrase ne demande-t-elle QUE de changer d ecran ?

    « va sur Chrome sur l ecran 1 » en nomme deux. Prise pour un simple
    changement d ecran, elle repondait « Ecran 1 » et laissait Chrome ou il
    etait : Alma annonçait une chose et en faisait une autre. On rend donc la
    main des qu une APPLICATION est nommee a cote de l ecran -- « va sur
    l ecran 1 » et « passe sur le deuxieme ecran » n en nomment aucune.
    """
    from commands.apps import est_une_application, separer_ecran

    reste, ecran = separer_ecran(ctx.norm)
    if ecran is None:
        return True
    nom = _TOURNURE.sub("", reste).strip()
    return not nom or not est_une_application(nom, ctx.config)


@command(
    name="choisir_ecran",
    guard=_seulement_l_ecran,
    patterns=[
        # On tolere quelques mots entre le verbe et « ecran » :
        # « passe sur le deuxieme ecran » doit marcher aussi.
        r"^(?:va|vas|aller|passe|passer|bascule|basculer|travaille|reste|"
        r"met[s]?\s+toi|place\s+toi|concentre\s+toi)\s+.{0,24}?"
        r"\b(?:ecran|moniteur|affichage|screen)s?\b.*$",
        # Un mot suffit apres « ecran » : s il ne designe aucun numero, la
        # commande le dira, plutot que de laisser la phrase sans reponse.
        r"^(?:ecran|moniteur|screen)\s+\S+.*$",
        r"^(?:utilise|prends)\s+(?:l\s+)?(?:ecran|moniteur)\b.*$",
        # Formulations tronquees par la transcription : « pour le premier
        # ecran » ou « le deuxieme ecran » doivent suffire.
        r"^(?:pour|sur|dans|vers)\s+.{0,20}?\b(?:ecran|moniteur)s?\b.*$",
        r"^(?:le\s+|l\s+)?(?:premier|premiere|deuxieme|second|seconde|troisieme|dernier)\s+(?:ecran|moniteur)\b.*$",
        # « switch to screen 2 », « go to monitor 1 », « use screen 2 »
        r"^(?:switch|go|move)\s+to\s+.{0,24}?\b(?:screen|monitor)\s+\S+.*$",
        r"^(?:use|work\s+on)\s+.{0,24}?\b(?:screen|monitor)\s+\S+.*$",
        r"^(?:screen|monitor)\s+\d+.*$",
        r"^(?:the\s+)?(?:first|second|third|last|right|left)\s+(?:screen|monitor)\b.*$",
    ],
    category="Fenêtres",
    description="Choisir l'écran sur lequel travailler",
    examples=["va sur l'écran 2", "écran 1", "switch to screen 2"],
    priority=96,
)
def choisir_ecran(ctx: CommandContext) -> Response:
    """
    Fixe l'écran de travail pour toutes les commandes suivantes.

    Le choix ne s'efface pas avec la session : une fois posé, il tient
    jusqu'à ce qu'on en demande un autre.
    """
    from commands.media import numero_ecran
    from core import desktop

    index = numero_ecran(ctx)
    ecrans = desktop.ecrans()
    if index is None:
        return Response.error(
            "Quel écran ? Vous en avez " + str(len(ecrans)) + ". Dites « écran 1 » ou « écran 2 »."
        )
    try:
        change = ctx.assistant.definir_ecran(index)
    except ValueError:
        return Response.error(
            "Je ne vois que " + str(len(ecrans)) + " écran(s), pas d'écran " + str(index) + "."
        )
    if not change:
        return Response(text="Déjà sur l'écran " + str(index) + ".", speak=False)
    return Response(text="Écran " + str(index) + ".", speak=False)


@command(
    name="quel_ecran",
    informatif=True,
    patterns=[
        r"(?:sur\s+)?quel\s+ecran\s+(?:es\s+tu|tu\s+es|suis\s+je|on\s+est|travailles\s+tu)",
        r"^(?:quel\s+est\s+l\s+ecran|ecran\s+actuel|quel\s+ecran)\s*\??$",
        r"which\s+screen\s+(?:are\s+you\s+on|do\s+you\s+work\s+on)",
        r"^(?:what|which)\s+(?:is\s+the\s+)?(?:current\s+)?screen\s*\??$",
    ],
    keywords=[["quel", "ecran"], ["which", "screen"]],
    category="Fenêtres",
    description="Dire sur quel écran l'assistant travaille",
    examples=["sur quel écran es-tu", "which screen are you on"],
    priority=98,
)
def quel_ecran(ctx: CommandContext) -> Response:
    """Rappelle l'écran de travail courant."""
    from core import desktop

    ecrans = desktop.ecrans()
    index = ctx.assistant.ecran_actif
    detail = ""
    for ecran in ecrans:
        if ecran.index == index:
            detail = " (" + str(ecran.largeur) + " sur " + str(ecran.hauteur) + ")"
    return Response(text="Je travaille sur l'écran " + str(index) + detail + ".")
