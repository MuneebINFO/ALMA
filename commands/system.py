"""
Controle du systeme : volume, luminosité, session, captures, dossiers.

Toute action destructrice (arret, redemarrage, veille) passe obligatoirement
par une confirmation explicite via ctx.confirm().
"""

from __future__ import annotations

from core import text_utils, win_utils
from core.context import CommandContext, Response
from core.registry import command


def _percent(ctx: CommandContext, default: int = 50) -> int:
    """Extrait un pourcentage de la phrase (premier nombre trouve)."""
    for token in ctx.tokens:
        if token.isdigit():
            return max(0, min(100, int(token)))
    return default


# « baisse le volume de la video » agit sur le curseur de volume DU LECTEUR
# affiche sur l ecran de travail -- celui de YouTube, Netflix, Twitch... --
# et laisse le volume general de l ordinateur intact.
OBJET_MEDIA = (r"(?:video|videos|film|films|serie|series|episode|musique|"
               r"chanson|lecture|podcast|streaming|navigateur|onglet|"
               r"movie|movies|show|song|browser|tab)")
DETERMINANT = r"(?:de\s+la\s+|de\s+l\s+|du\s+|des\s+|de\s+)"
VERBES_REGLAGE = (r"(?:met[s]?|mettre|regle|regler|passe|baisse|baisser|"
                  r"diminue|diminuer|reduis|reduire|monte|monter|augmente|augmenter)")


def _fenetre_de_lecture(ctx: CommandContext):
    """
    La fenetre dont il faut regler le volume, sur l ecran de travail.

    Retourne (fenetre, numero d ecran). La fenetre vaut None si rien ne joue
    la : comme pour la pause, on ne va pas chercher sur un autre ecran.
    """
    from commands.media import ecran_cible
    from core import media_control

    index = ecran_cible(ctx)
    fenetres = media_control.fenetres_de_lecture_sur_ecran(index)
    return (fenetres[0] if fenetres else None), index


def _rien_ne_joue(index: int) -> Response:
    return Response.error(
        "Rien ne joue sur l'écran " + str(index) + " : il n'y a pas de volume à régler."
    )


def _pas_de_curseur() -> Response:
    return Response.error(
        "Je n'ai pas trouvé de réglage de volume dans ce lecteur. "
        "Vous pouvez régler le volume de l'ordinateur à la place."
    )


@command(
    name="volume_media_set",
    patterns=[
        VERBES_REGLAGE + r"\s+(?:le\s+)?(?:son|volume)\s+" + DETERMINANT
        + OBJET_MEDIA + r"\s+(?:a|sur)\s+(" + r"\d" + r"{1,3})",
        r"(?:son|volume)\s+" + DETERMINANT + OBJET_MEDIA
        + r"\s+(?:a|sur)\s+(\d{1,3})",
        # « set the video volume to 30 », « set the volume of the movie to 60 »
        r"(?:set|put)\s+(?:the\s+)?" + OBJET_MEDIA + r"(?:'?s)?\s+volume\s+to\s+(\d{1,3})",
        r"(?:set|put)\s+(?:the\s+)?volume\s+of\s+the\s+" + OBJET_MEDIA + r"\s+to\s+(\d{1,3})",
    ],
    category="Système",
    description="Régler le volume de la vidéo, sans toucher au volume général",
    examples=["baisse le volume de la vidéo à 30", "mets le volume du film à 60",
              "set the video volume to 30"],
    priority=95,
)
def volume_media_set(ctx: CommandContext) -> Response:
    """Regle le volume du lecteur qui joue sur l'écran de travail."""
    from core import player_volume

    fenetre, index = _fenetre_de_lecture(ctx)
    if fenetre is None:
        return _rien_ne_joue(index)
    cible = max(0, min(100, int(ctx.arg or 50)))
    niveau = player_volume.regler(fenetre, cible)
    if niveau is None:
        return _pas_de_curseur()
    if abs(niveau - cible) > 10:
        return Response.error(
            "Je n'ai pas pu descendre plus bas que " + str(niveau) + " pour cent."
            if niveau > cible else
            "Je n'ai pas pu monter plus haut que " + str(niveau) + " pour cent."
        )
    return Response(text="Volume de la vidéo à " + str(niveau) + " pour cent.")


@command(
    name="volume_media_up",
    patterns=[
        r"(?:monte|monter|augmente|augmenter)\s+(?:le\s+)?(?:son|volume)\s+"
        + DETERMINANT + OBJET_MEDIA + r"\b",
        r"(?:met[s]?|mettre)\s+(?:la\s+|le\s+|l\s+)?" + OBJET_MEDIA
        + r"\s+plus\s+fort",
        r"(?:turn\s+up|raise|increase)\s+(?:the\s+)?" + OBJET_MEDIA + r"(?:'?s)?\s+volume",
        r"(?:make|turn)\s+(?:the\s+)?" + OBJET_MEDIA + r"\s+louder",
    ],
    category="Système",
    description="Augmenter le volume de la vidéo seule",
    examples=["monte le volume de la vidéo", "mets la vidéo plus fort",
              "turn up the video volume"],
    priority=94,
)
def volume_media_up(ctx: CommandContext) -> Response:
    """Monte de 10 points le volume du lecteur de l'écran de travail."""
    return _ajuster_volume_media(ctx, 10)


@command(
    name="volume_media_down",
    patterns=[
        r"(?:baisse|baisser|diminue|diminuer|reduis|reduire)\s+(?:le\s+)?"
        r"(?:son|volume)\s+" + DETERMINANT + OBJET_MEDIA + r"\b",
        r"(?:met[s]?|mettre)\s+(?:la\s+|le\s+|l\s+)?" + OBJET_MEDIA
        + r"\s+moins\s+fort",
        r"(?:turn\s+down|lower|decrease)\s+(?:the\s+)?" + OBJET_MEDIA + r"(?:'?s)?\s+volume",
        r"(?:make|turn)\s+(?:the\s+)?" + OBJET_MEDIA + r"\s+quieter",
    ],
    category="Système",
    description="Baisser le volume de la vidéo seule",
    examples=["baisse le volume de la vidéo", "mets le film moins fort",
              "turn down the video volume"],
    priority=94,
)
def volume_media_down(ctx: CommandContext) -> Response:
    """Baisse de 10 points le volume du lecteur de l'écran de travail."""
    return _ajuster_volume_media(ctx, -10)


def _ajuster_volume_media(ctx: CommandContext, delta: int) -> Response:
    from core import player_volume

    fenetre, index = _fenetre_de_lecture(ctx)
    if fenetre is None:
        return _rien_ne_joue(index)
    niveau = player_volume.ajuster(fenetre, delta)
    if niveau is None:
        return _pas_de_curseur()
    return Response(text="Volume de la vidéo à " + str(niveau) + " pour cent.")


@command(
    name="volume_set",
    patterns=[
        r"(?:met|mets|mettre|regle|regler|passe)\s+(?:le\s+)?(?:son|volume)\s+(?:a|sur)\s+(\d{1,3})",
        r"volume\s+(?:a|sur)\s+(\d{1,3})",
        r"(?:set)\s+(?:the\s+)?volume\s+to\s+(\d{1,3})",
        r"^volume\s+(\d{1,3})%?$",
    ],
    category="Système",
    description="Régler le volume a un pourcentage precis",
    examples=["mets le volume a 30%", "volume a 70", "set the volume to 70"],
    priority=90,
)
def volume_set(ctx: CommandContext) -> Response:
    """Regle le volume principal."""
    level = int(ctx.arg or 50)
    level = max(0, min(100, level))
    if win_utils.set_volume(level):
        return Response(text="Volume réglé à " + str(level) + " pour cent.")
    return Response.error(
        "Je n'ai pas pu réglér le volume. Installez pycaw (pip install -r requirements.txt)."
    )


@command(
    name="volume_up",
    patterns=[r"(?:monte|augmente|augmenter|monter|plus\s+fort)\s*(?:le\s+)?(?:son|volume)?",
              r"(?:met|mets)\s+plus\s+fort",
              r"(?:turn\s+up|raise|increase)\s*(?:the\s+)?(?:volume|sound)?$",
              r"^louder$"],
    keywords=[["monte", "son"], ["augmente", "volume"], ["turn", "up"]],
    category="Système",
    description="Augmenter le volume",
    examples=["monte le son", "augmente le volume", "turn up the volume"],
    priority=85,
)
def volume_up(ctx: CommandContext) -> Response:
    """Augmente le volume de 10 points."""
    new_level = win_utils.change_volume(10)
    if new_level is None:
        return Response(text="J'augmente le volume.")
    return Response(text="Volume à " + str(new_level) + " pour cent.")


@command(
    name="volume_down",
    patterns=[r"(?:baisse|baisser|diminue|reduis|moins\s+fort)\s*(?:le\s+)?(?:son|volume)?",
              r"(?:turn\s+down|lower|decrease)\s*(?:the\s+)?(?:volume|sound)?$",
              r"^quieter$"],
    keywords=[["baisse", "son"], ["baisse", "volume"], ["turn", "down"]],
    category="Système",
    description="Baisser le volume",
    examples=["baisse le son", "baisse le volume", "turn down the volume"],
    priority=85,
)
def volume_down(ctx: CommandContext) -> Response:
    """Diminue le volume de 10 points."""
    new_level = win_utils.change_volume(-10)
    if new_level is None:
        return Response(text="Je baisse le volume.")
    return Response(text="Volume à " + str(new_level) + " pour cent.")


@command(
    name="volume_mute",
    patterns=[r"(?:coupe|couper|mute|silence)\s*(?:le\s+)?(?:son|volume|micro)?$",
              r"^(?:chut|silence)$",
              r"^mute\s*(?:the\s+)?(?:sound|volume)?$"],
    keywords=[["coupe", "son"], ["mute"]],
    category="Système",
    description="Couper le son",
    examples=["coupe le son", "silence", "mute"],
    priority=88,
)
def volume_mute(ctx: CommandContext) -> Response:
    """Coupe le son."""
    if win_utils.set_mute(True):
        return Response(text="Son coupé.")
    return Response.error("Je n'ai pas pu couper le son.")


@command(
    name="volume_unmute",
    patterns=[r"(?:remet|remets|retablis|reactive|restaure)\s*(?:le\s+)?(?:son|volume)",
              r"^(?:unmute|son\s+on)$",
              r"^(?:restore|turn\s+on)\s+(?:the\s+)?(?:sound|volume)$"],
    category="Système",
    description="Rétablir le son",
    examples=["remets le son", "unmute"],
    priority=89,
)
def volume_unmute(ctx: CommandContext) -> Response:
    """Retablit le son."""
    if win_utils.set_mute(False):
        return Response(text="Son rétabli.")
    return Response.error("Je n'ai pas pu rétablir le son.")


@command(
    name="volume_status",
    informatif=True,
    patterns=[r"(?:quel|quelle)\s+(?:est\s+)?(?:le\s+)?(?:niveau\s+(?:du|de)\s+)?volume",
              r"what\s+(?:is\s+|s\s+)?the\s+volume(?:\s+level)?"],
    category="Système",
    description="Connaître le niveau de volume",
    examples=["quel est le volume", "what's the volume"],
    priority=91,
)
def volume_status(ctx: CommandContext) -> Response:
    """Indique le niveau de volume actuel."""
    level = win_utils.get_volume()
    if level is None:
        return Response.error("Je ne peux pas lire le volume (pycaw non disponible).")
    muted = win_utils.is_muted()
    suffix = " (son coupe)" if muted else ""
    return Response(text="Le volume est à " + str(level) + " pour cent" + suffix + ".")


@command(
    name="brightness_set",
    patterns=[
        r"(?:met|mets|regle|passe)\s+(?:la\s+)?(?:luminosite|lumiere|brightness)\s+(?:a|sur)\s+(\d{1,3})",
        r"(?:luminosite|brightness)\s+(?:a|sur)\s+(\d{1,3})",
        r"set\s+(?:the\s+)?brightness\s+to\s+(\d{1,3})",
    ],
    category="Système",
    description="Régler la luminosité de l'écran",
    examples=["mets la luminosité a 50%", "set the brightness to 50"],
    priority=90,
)
def brightness_set(ctx: CommandContext) -> Response:
    """Regle la luminosité de l'écran."""
    level = max(0, min(100, int(ctx.arg or 50)))
    if win_utils.set_brightness(level):
        return Response(text="Luminosité réglée à " + str(level) + " pour cent.")
    return Response.error(
        "Luminosité non modifiable sur cet ecran (fréquent sur les écrans externes)."
    )


@command(
    name="brightness_change",
    patterns=[r"(?:monte|augmente|baisse|diminue|reduis)\s+(?:la\s+)?(?:luminosite|lumiere)",
              r"(?:increase|raise|turn\s+up|decrease|lower|turn\s+down)\s+(?:the\s+)?brightness"],
    category="Système",
    description="Augmenter ou baisser la luminosité",
    examples=["monte la luminosité", "baisse la luminosité", "increase the brightness"],
    priority=86,
)
def brightness_change(ctx: CommandContext) -> Response:
    """Ajuste la luminosité de 10 points."""
    current = win_utils.get_brightness()
    if current is None:
        return Response.error("Je ne peux pas lire la luminosité de cet ecran.")
    down = any(text_utils.fuzzy_in(word, ctx.tokens)
              for word in ("baisse", "diminue", "reduis", "decrease", "lower", "down"))
    target = max(0, min(100, current + (-10 if down else 10)))
    if win_utils.set_brightness(target):
        return Response(text="Luminosité à " + str(target) + " pour cent.")
    return Response.error("Luminosité non modifiable sur cet ecran.")


@command(
    name="screenshot",
    patterns=[
        r"(?:prend|prends|prendre|fais|faire|capture)\s+(?:moi\s+)?(?:une\s+|un\s+)?(?:capture|screenshot|photo\s+de\s+l\s+ecran)",
        r"^(?:capture|screenshot)$",
        r"(?:take|grab)\s+(?:a\s+)?screenshot",
    ],
    keywords=[["capture", "ecran"], ["screenshot"]],
    category="Système",
    description="Prendre une capture d'écran",
    examples=["prends une capture d'écran", "screenshot", "take a screenshot"],
    priority=88,
)
def screenshot(ctx: CommandContext) -> Response:
    """Capture l'écran dans le dossier configure, avec horodatage."""
    folder = ctx.config.resolve_path("screenshots", "screenshots")
    ok, detail = win_utils.take_screenshot(folder)
    if ok:
        from pathlib import Path

        return Response(text="Capture enregistrée : " + Path(detail).name)
    return Response.error("Capture impossible : " + detail)


@command(
    name="lock_session",
    patterns=[r"(?:verrouille|verrouiller|verouille|lock)\s*(?:l\s+|the\s+)?"
              r"(?:ordinateur|ecran|session|pc|computer|screen)?",
              r"^lock$"],
    keywords=[["verrouille", "ordinateur"], ["verrouille", "session"], ["lock", "computer"]],
    category="Système",
    description="Verrouiller la session Windows",
    examples=["verrouille l ordinateur", "lock the computer"],
    priority=88,
)
def lock_session(ctx: CommandContext) -> Response:
    """Verrouille la session (action non destructrice, sans confirmation)."""
    if win_utils.lock_workstation():
        return Response(text="Session verrouillée.", speak=False)
    return Response.error("Je n'ai pas pu verrouiller la session.")


@command(
    name="sleep_pc",
    patterns=[r"(?:met|mets|mettre)\s+(?:l\s+)?(?:ordinateur|pc)?\s*en\s+veille", r"^veille$",
              r"(?:put|send)\s+(?:the\s+)?(?:computer|pc)?\s*to\s+sleep", r"^sleep$"],
    keywords=[["mets", "veille"], ["sleep"]],
    category="Système",
    description="Mettre l'ordinateur en veille (confirmation demandée)",
    examples=["mets l'ordinateur en veille", "put the computer to sleep"],
    priority=88,
)
def sleep_pc(ctx: CommandContext) -> Response:
    """Met la machine en veille apres confirmation."""
    if not ctx.confirm("Voulez-vous vraiment mettre l'ordinateur en veille ?"):
        return Response(text="Mise en veille annulée.")
    ok, out = win_utils.run_command(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    if ok:
        return Response(text="Mise en veille.", speak=False)
    return Response.error("Mise en veille impossible : " + out)


@command(
    name="shutdown_pc",
    patterns=[r"(?:eteins|eteindre|arrete|arreter|shutdown)\s+(?:l\s+)?(?:ordinateur|pc|systeme)",
              r"^(?:eteins|shutdown)$",
              r"(?:shut\s+down|turn\s+off)\s+(?:the\s+)?(?:computer|pc|system)"],
    keywords=[["eteins", "ordinateur"], ["shut", "down"]],
    category="Système",
    description="Éteindre l'ordinateur (confirmation obligatoire)",
    examples=["eteins l ordinateur", "shut down the computer"],
    priority=88,
)
def shutdown_pc(ctx: CommandContext) -> Response:
    """Eteint la machine apres confirmation, avec 30 secondes de delai."""
    if not ctx.confirm("ATTENTION : voulez-vous vraiment eteindre l'ordinateur ?"):
        return Response(text="Extinction annulée.")
    ok, out = win_utils.run_command(["shutdown", "/s", "/t", "30"])
    if ok:
        return Response(
            text="Extinction dans 30 secondes. Tapez « annule l'extinction » pour l interrompre."
        )
    return Response.error("Extinction impossible : " + out)


@command(
    name="restart_pc",
    patterns=[r"(?:redemarre|redemarrer|reboot|restart)\s*(?:l\s+)?(?:ordinateur|pc|systeme|"
              r"the\s+computer|computer)?"],
    keywords=[["redemarre", "ordinateur"], ["restart", "computer"]],
    category="Système",
    description="Redémarrer l'ordinateur (confirmation obligatoire)",
    examples=["redemarre l ordinateur", "restart the computer"],
    priority=88,
)
def restart_pc(ctx: CommandContext) -> Response:
    """Redemarre la machine apres confirmation, avec 30 secondes de delai."""
    if not ctx.confirm("ATTENTION : voulez-vous vraiment redemarrer l'ordinateur ?"):
        return Response(text="Redémarrage annulé.")
    ok, out = win_utils.run_command(["shutdown", "/r", "/t", "30"])
    if ok:
        return Response(
            text="Redémarrage dans 30 secondes. Tapez « annule l'extinction » pour l interrompre."
        )
    return Response.error("Redemarrage impossible : " + out)


@command(
    name="abort_shutdown",
    patterns=[r"(?:annule|annuler|stop|arrete)\s+(?:l\s+)?(?:extinction|arret|redemarrage|shutdown)",
              r"(?:cancel|abort)\s+(?:the\s+)?(?:shutdown|restart)"],
    category="Système",
    description="Annuler une extinction ou un redémarrage programmé",
    examples=["annule l'extinction", "cancel the shutdown"],
    priority=93,
)
def abort_shutdown(ctx: CommandContext) -> Response:
    """Interrompt un arret programme."""
    ok, out = win_utils.run_command(["shutdown", "/a"])
    if ok:
        return Response(text="Extinction annulée.")
    return Response.error("Aucune extinction n'était programmée.")


@command(
    name="open_folder",
    patterns=[
        r"^(?:ouvre|ouvrir|montre|affiche)\s+(?:le\s+dossier|mon\s+dossier|le\s+repertoire)\s+(.+)$",
        r"^(?:ouvre|ouvrir)\s+(?:mes\s+|mon\s+|le\s+)?(telechargements?|downloads?|documents?|"
        r"images|photos|bureau|desktop|videos|musique|music)$",
        r"^(?:open|show)\s+(?:the\s+|my\s+)?folder\s+(.+)$",
        r"^open\s+(?:my\s+)?(downloads?|documents?|photos|desktop|music|videos)$",
    ],
    category="Système",
    description="Ouvrir un dossier dans l explorateur",
    examples=["ouvre le dossier telechargements", "ouvre mes documents",
              "open my downloads"],
    priority=87,
)
def open_folder(ctx: CommandContext) -> Response:
    """Ouvre un dossier connu (ou un chemin complet) dans l explorateur."""
    target = ctx.arg.strip()
    folders = ctx.config.get("folders", {}) or {}
    key = text_utils.normalize(target).strip()
    path = folders.get(key)
    if path is None:
        best = text_utils.best_match(key, list(folders.keys()), threshold=0.8)
        path = folders.get(best) if best else None
    if path is None:
        path = target  # peut-être un chemin complet donne par l'utilisateur
    ok, resolved = win_utils.open_folder(path)
    if ok:
        return Response(text="J'ouvre " + resolved + ".")
    return Response.error("Dossier introuvable : " + resolved)
