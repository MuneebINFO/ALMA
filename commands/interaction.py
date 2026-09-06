"""
Defilement de la page et clic sur un element affiche.

Le defilement est continu : la commande rend la main tout de suite et
l assistant reste a l ecoute pour pouvoir l arreter d un mot.
"""

from __future__ import annotations

from core import desktop, interaction, text_utils
from core.context import CommandContext, Response
from core.registry import command

# « scroll » et « defile » sont sans ambiguite. « monte » et « descends »
# ne le sont pas (« monte le son », « monte la luminosite ») : ces verbes
# exigent donc une cible explicite, sinon ils captureraient le volume.
VERBES_DEFILER = r"(?:scroll|scrolle|scroller|scrolling|defile|defiler|defiles)"

# Ordinaux, pour « clique sur la deuxieme video ».
ORDINAUX = {
    "premier": 1, "premiere": 1, "1": 1,
    "deuxieme": 2, "second": 2, "seconde": 2, "2": 2,
    "troisieme": 3, "3": 3, "quatrieme": 4, "4": 4, "cinquieme": 5, "5": 5,
    "dernier": -1, "derniere": -1,
}


def fenetre_visee(ctx: CommandContext):
    """
    Fenetre sur laquelle agir : celle du site en cours si on en a un en
    memoire, sinon la fenetre de navigateur au premier plan.
    """
    cle = ctx.assistant.rappeler("site")
    if cle:
        from commands.websites import termes_de_recherche

        entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
        for terme in termes_de_recherche(cle, entree):
            fenetre = desktop.trouver_fenetre(terme, navigateurs_seulement=True)
            if fenetre is not None:
                return fenetre
    fenetres = [f for f in desktop.fenetres() if f.est_navigateur]
    return fenetres[0] if fenetres else None


def direction_demandee(ctx: CommandContext) -> int:
    """
    Sens du defilement. Vers le BAS par defaut : c est ce qu on veut neuf
    fois sur dix, et il faut le dire explicitement pour remonter.
    """
    mots_haut = ("haut", "monte", "montes", "remonte", "remontes", "remonter", "up", "arriere")
    if any(text_utils.fuzzy_in(mot, ctx.tokens) for mot in mots_haut):
        return interaction.HAUT
    return interaction.BAS


@command(
    name="defiler",
    patterns=[
        r"^" + VERBES_DEFILER + r"\b",
        r"(?:fais|faire)\s+(?:moi\s+)?defiler",
        r"^(?:descend[s]?|remonte[s]?)$",
        r"^(?:descend[s]?|monte[s]?|remonte[s]?)\s+(?:un\s+peu\s+)?"
        r"(?:la\s+page|dans\s+la\s+page|vers\s+le\s+(?:haut|bas)|en\s+(?:haut|bas))",
        r"^(?:continue\s+(?:a|de)\s+)?(?:descendre|monter)\s+(?:la\s+page|dans\s+la\s+page)$",
    ],
    keywords=[["scroll"], ["defile"]],
    category="Navigation",
    description="Faire défiler la page (vers le bas par défaut)",
    examples=["scrolle", "fais défiler vers le haut"],
    priority=92,
)
def defiler(ctx: CommandContext) -> Response:
    """Lance un défilement continu, jusqu'à ce qu'on l'arrête."""
    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return Response.error("Je ne vois aucune fenêtre de navigateur à faire défiler.")

    direction = direction_demandee(ctx)
    vitesse = ctx.config.get("interaction.scroll_crans", 2)
    intervalle = ctx.config.get("interaction.scroll_intervalle", 0.22)
    if not ctx.assistant.defilement.demarrer(
        fenetre=fenetre, direction=direction, crans=int(vitesse), intervalle=float(intervalle)
    ):
        return Response.error("Je n'ai pas pu lancer le défilement.")
    sens = "vers le haut" if direction == interaction.HAUT else "vers le bas"
    return Response(text="Je fais défiler " + sens + ". Dites « arrête » quand ça suffit.")


@command(
    name="arreter_defilement",
    patterns=[r"^(?:arrete|arreter|stop|stoppe|ca\s+suffit|c\s+est\s+bon|assez)\b"],
    keywords=[["arrete"], ["stop"]],
    category="Navigation",
    description="Arrêter le défilement en cours",
    examples=["arrête"],
    priority=99,
    guard=lambda ctx: ctx.assistant.defilement.actif,
    contextuel=True,
)
def arreter_defilement(ctx: CommandContext) -> Response:
    """Interrompt le défilement."""
    if ctx.assistant.defilement.arreter():
        return Response(text="J'arrête.", speak=False)
    return Response(text="Rien ne défilait.", speak=False)


def _ordinal_demande(ctx: CommandContext):
    """Extrait « la deuxième », « le dernier »... d une phrase."""
    for token in ctx.tokens:
        if token in ORDINAUX:
            return ORDINAUX[token]
    return None


@command(
    name="cliquer_ordinal",
    patterns=[
        r"^(?:clique|cliquer|clic|appuie|selectionne|ouvre|lance|met[s]?|joue|regarde)\s+"
        r"(?:sur\s+)?(?:la|le|l)\s+(?P<rang>premier|premiere|deuxieme|second|seconde|troisieme|"
        r"quatrieme|cinquieme|dernier|derniere)\s+(?P<quoi>video|film|resultat|lien|"
        r"proposition|image|element|serie|episode)",
    ],
    category="Navigation",
    description="Cliquer sur le premier, deuxième... élément affiché",
    examples=["clique sur la première vidéo"],
    priority=94,
)
def cliquer_ordinal(ctx: CommandContext) -> Response:
    """
    Clique sur le n-ième élément affiché.

    Heuristique assumée : on ne sait pas distinguer une vidéo d'un autre lien.
    On prend donc les éléments affichés dans l'ordre de lecture, en écartant
    les libellés courts, qui sont presque toujours des boutons de navigation.
    """
    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return Response.error("Je ne vois aucune fenêtre où cliquer.")

    rang = _ordinal_demande(ctx) or 1
    cibles = [c for c in interaction.elements_cliquables(fenetre) if len(c.nom) >= 12]
    if not cibles:
        return Response.error("Je ne trouve rien de cliquable à l'écran.")
    if rang == -1:
        cible = cibles[-1]
    elif rang <= len(cibles):
        cible = cibles[rang - 1]
    else:
        return Response.error(
            "Je ne vois que " + str(len(cibles)) + " éléments à l'écran."
        )

    if interaction.cliquer(cible):
        return Response(text="J'ouvre « " + cible.nom[:60] + " ».")
    return Response.error("Je n'ai pas réussi à cliquer sur « " + cible.nom[:40] + " ».")


@command(
    name="cliquer_sur",
    patterns=[
        r"^(?:clique|cliquer|clic|appuie|appuyer)\s+(?:sur\s+)?(.+)$",
        r"^(?:selectionne|selectionner|choisis|choisir)\s+(.+)$",
    ],
    category="Navigation",
    description="Cliquer sur un élément visible, en le nommant",
    examples=["clique sur Abonnements"],
    priority=91,
)
def cliquer_sur(ctx: CommandContext) -> Response:
    """Clique sur l'élément dont le nom correspond à ce qui est demandé."""
    voulu = ctx.arg.strip()
    if not voulu:
        return Response.error("Sur quoi dois-je cliquer ?")

    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return Response.error("Je ne vois aucune fenêtre où cliquer.")

    cibles = interaction.elements_cliquables(fenetre)
    cible = interaction.chercher_cible(cibles, voulu)
    if cible is None:
        return Response.error(
            "Je ne trouve pas « " + voulu + " » à l'écran. "
            "Dites « clique sur la première vidéo » si vous préférez par position."
        )
    if interaction.cliquer(cible):
        return Response(text="Je clique sur « " + cible.nom[:60] + " ».")
    return Response.error("Je n'ai pas réussi à cliquer sur « " + cible.nom[:40] + " ».")
