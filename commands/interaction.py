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


# Nature de l element, selon le mot employe. « le bouton lecture » ne doit pas
# tomber sur un titre de video qui contient le mot « lecture ».
TYPES_PAR_MOT = {
    "bouton": (interaction.BOUTON,),
    "boutons": (interaction.BOUTON,),
    "lien": (interaction.LIEN,),
    "image": (interaction.IMAGE,),
    "vignette": (interaction.IMAGE,),
    "onglet": (interaction.ONGLET,),
    "case": (interaction.CASE,),
    "champ": (interaction.CHAMP,),
    "video": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE, interaction.ITEM_LISTE),
    "film": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE, interaction.ITEM_LISTE),
    "serie": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE, interaction.ITEM_LISTE),
    "episode": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE, interaction.ITEM_LISTE),
    "clip": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE),
    "chanson": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE),
    "musique": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE),
    "titre": (interaction.LIEN, interaction.GROUPE),
    "resultat": (interaction.LIEN, interaction.GROUPE, interaction.ITEM_LISTE),
    "proposition": (interaction.LIEN, interaction.GROUPE, interaction.ITEM_LISTE),
}

# Les interfaces sont souvent en anglais, meme quand on parle francais :
# « le bouton lecture » doit trouver « Play ».
SYNONYMES_CONTROLE = {
    "lecture": ("lecture", "lire", "play", "jouer", "demarrer"),
    "pause": ("pause", "suspendre", "mettre en pause"),
    "suivant": ("suivant", "suivante", "next"),
    "precedent": ("precedent", "precedente", "previous"),
    "plein ecran": ("plein ecran", "fullscreen", "full screen", "agrandir"),
    "muet": ("muet", "mute", "couper le son"),
    "son": ("son", "volume", "unmute"),
    "recherche": ("recherche", "rechercher", "search"),
    "accueil": ("accueil", "home"),
    "abonnements": ("abonnements", "subscriptions", "s abonner", "subscribe"),
    "parametres": ("parametres", "settings", "options"),
    "fermer": ("fermer", "close", "quitter"),
    "suivre": ("suivre", "follow", "s abonner"),
    "aime": ("aime", "j aime", "like"),
    "partager": ("partager", "share"),
}


def variantes_libelle(libelle: str) -> list:
    """Le libelle demande, plus ses equivalents anglais s il en a."""
    norme = text_utils.normalize(libelle).strip()
    for canonique, synonymes in SYNONYMES_CONTROLE.items():
        if norme in synonymes or norme == canonique:
            return list(dict.fromkeys([libelle] + list(synonymes)))
    return [libelle]



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
    return Response.action("Je fais défiler " + sens + ".")


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
        return Response.action("J'ouvre « " + cible.nom[:60] + " ».")
    return Response.error("Je n'ai pas réussi à cliquer sur « " + cible.nom[:40] + " ».")


@command(
    name="cliquer_sur",
    patterns=[
        # Le type est optionnel : « clique sur le bouton lecture »,
        # « clique sur la video Interstellar », « clique sur Abonnements ».
        # Uniquement des verbes de clic : « ouvre », « lance » ou « mets »
        # appartiennent aux applications et aux sites, pas ici.
        r"^(?:clique|cliquer|clic|appuie|appuyer|selectionne|selectionner|"
        r"choisis|choisir|tape\s+sur)\s+(?:sur\s+)?"
        r"(?:le\s+|la\s+|les\s+|l\s+|un\s+|une\s+)?"
        r"(?P<type>bouton|boutons|lien|image|vignette|onglet|case|champ|video|film|"
        r"serie|episode|clip|chanson|musique|titre|resultat|proposition)?\s*"
        r"(?P<label>.+)$",
    ],
    category="Navigation",
    description="Cliquer sur un élément visible, en le nommant",
    examples=["clique sur Abonnements", "clique sur le bouton lecture"],
    priority=91,
)
def cliquer_sur(ctx: CommandContext) -> Response:
    """
    Clique sur l'élément nommé.

    Le type éventuellement précisé (« le bouton », « la vidéo ») restreint la
    recherche : « le bouton lecture » ne doit pas atterrir sur un titre de
    vidéo contenant le mot « lecture ».
    """
    libelle = ctx.group("label").strip()
    mot_type = text_utils.normalize(ctx.group("type")).strip()
    if not libelle:
        return Response.error("Sur quoi dois-je cliquer ?")

    fenetre = fenetre_visee(ctx)
    if fenetre is None:
        return Response.error("Je ne vois aucune fenêtre où cliquer.")

    types = TYPES_PAR_MOT.get(mot_type)
    variantes = variantes_libelle(libelle)

    def chercher():
        cibles = interaction.elements_cliquables(fenetre)
        for variante in variantes:
            trouve = interaction.chercher_cible(cibles, variante, types=types)
            if trouve is not None:
                return trouve
        return None

    cible = chercher()
    if cible is None:
        # Les pages se chargent en asynchrone : ce qu on cherche peut n etre
        # pas encore apparu. On laisse une seconde chance avant d abandonner.
        import time

        time.sleep(1.2)
        cible = chercher()

    if cible is None:
        quoi = (mot_type + " ") if mot_type else ""
        return Response.error(
            "Je ne trouve pas " + quoi + "« " + libelle + " » à l'écran. "
            "Dites « clique sur la première vidéo » pour choisir par position."
        )
    if interaction.cliquer(cible):
        return Response.action("Je clique sur « " + cible.nom[:60] + " ».")
    return Response.error("Je n'ai pas réussi à cliquer sur « " + cible.nom[:40] + " ».")
