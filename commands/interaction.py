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
    # Selecteur de profil, a l ouverture d un service de streaming.
    "profil": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE,
               interaction.ITEM_LISTE, interaction.BOUTON),
    "compte": (interaction.LIEN, interaction.GROUPE, interaction.IMAGE,
               interaction.ITEM_LISTE, interaction.BOUTON),
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



# Alma ne doit jamais se cliquer elle-meme : sa propre fenetre est au premier
# plan des qu on la regarde.
PROCESSUS_ALMA = ("pythonw.exe", "python.exe", "alma.exe")


def _est_alma(fenetre, ctx) -> bool:
    nom = str(ctx.config.get("general.assistant_name", "Alma") or "Alma").lower()
    return (fenetre.processus.lower() in PROCESSUS_ALMA
            and nom in (fenetre.titre or "").lower())


def fenetre_au_premier_plan(ctx):
    """
    La fenetre que l utilisateur regarde, si elle est sur l ecran de travail.

    C est la reponse la plus juste a « clique sur X » : on clique dans ce
    qu on a sous les yeux. Quand Alma est elle-meme devant -- mode vocal,
    plein ecran -- on prend la DERNIERE fenetre non-Alma qu on a vue, que
    l interface garde en memoire.
    """
    fenetre = ctx.assistant.fenetre_courante()
    if fenetre is None or _est_alma(fenetre, ctx):
        return None
    ecran = getattr(ctx.assistant, "ecran_actif", None)
    if ecran is not None and fenetre.ecran != ecran:
        return None
    return fenetre


def fenetre_visee(ctx: CommandContext):
    """
    Fenetre sur laquelle agir.

    Dans l ordre : le site dont on vient de parler -- une intention explicite
    prime sur tout --, puis la fenetre AU PREMIER PLAN, puis les navigateurs
    de l ecran de travail.

    Le premier plan a ete ajoute pour que « clique sur X » atteigne aussi les
    applications : la liste se limitait aux navigateurs, si bien que rien
    n etait cliquable dans une fenetre ordinaire.
    """
    ecran = getattr(ctx.assistant, "ecran_actif", None)
    cle = ctx.assistant.rappeler("site")
    if cle:
        from commands.websites import termes_de_recherche

        entree = (ctx.config.get("websites", {}) or {}).get(cle, {})
        for terme in termes_de_recherche(cle, entree):
            fenetre = desktop.trouver_fenetre(terme, navigateurs_seulement=True, ecran=ecran)
            if fenetre is not None:
                return fenetre

    devant = fenetre_au_premier_plan(ctx)
    if devant is not None:
        return devant

    navigateurs = [f for f in desktop.fenetres() if f.est_navigateur]
    if ecran is not None:
        sur_ecran = [f for f in navigateurs if f.ecran == ecran]
        if sur_ecran:
            return sur_ecran[0]
    return navigateurs[0] if navigateurs else None


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
    # Pas de mode d emploi : le defilement se voit, et « arrete » l arrete.
    return Response(text="Je fais défiler " + sens + ".")


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
    # Dans la PAGE seulement : « le premier lien » designe le premier resultat,
    # jamais le premier onglet du navigateur.
    visibles = [c for c in interaction.elements_cliquables(fenetre, page_seulement=True)
                if len(c.nom) >= 12]
    if not visibles:
        visibles = [c for c in interaction.elements_cliquables(fenetre)
                    if len(c.nom) >= 12]
    if not visibles:
        return Response.error("Je ne trouve rien de cliquable à l'écran.")

    # La nature dite compte : « le premier LIEN » ne doit pas designer un
    # bouton de la barre de recherche, qui vient pourtant avant dans la page.
    types = TYPES_PAR_MOT.get(text_utils.normalize(ctx.group("quoi")).strip())
    cibles = [c for c in visibles if c.type_controle in types] if types else visibles
    if not cibles:
        cibles = visibles
    if rang == -1:
        cible = cibles[-1]
    elif rang <= len(cibles):
        cible = cibles[rang - 1]
    else:
        return Response.error(
            "Je ne vois que " + str(len(cibles)) + " éléments à l'écran."
        )

    if interaction.cliquer(cible):
        return Response(text="J'ouvre « " + interaction.titre_affiche(cible.nom)[:60] + " ».")
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
        r"serie|episode|clip|chanson|musique|titre|resultat|proposition|profil|"
        r"compte)?\s*"
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

    # « clique sur l onglet X » vise l habillage du navigateur ; tout le
    # reste vise la page. On regarde donc la page d abord, et on n elargit
    # a la fenetre entiere que si elle ne contient pas ce qu on cherche.
    dans_la_page = mot_type not in ("onglet", "onglets")

    def chercher(page_seulement=True):
        cibles = interaction.elements_cliquables(
            fenetre, page_seulement=page_seulement and dans_la_page)
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
        # Toujours rien dans la page : c est peut-etre un bouton du navigateur.
        cible = chercher(page_seulement=False)

    if cible is not None:
        return _cliquer(cible)

    # Dernier recours : reveiller la barre de controle d un lecteur video.
    # Fermee, elle n est pas seulement invisible -- elle a disparu de l arbre
    # d accessibilite, et ses boutons avec. Le clic doit donc se faire tant
    # que le pointeur la maintient ouverte.
    with interaction.controles_reveilles(fenetre) as reveille:
        if reveille:
            cible = chercher()
            if cible is not None:
                return _cliquer(cible)

    quoi = (mot_type + " ") if mot_type else ""
    return Response.error("Je ne trouve pas " + quoi + "« " + libelle + " » à l'écran.")


def _cliquer(cible) -> Response:
    if interaction.cliquer(cible):
        return Response(text="Je clique sur « " + interaction.titre_affiche(cible.nom)[:60] + " ».")
    return Response.error("Je n'ai pas réussi à cliquer sur « " + cible.nom[:40] + " ».")
