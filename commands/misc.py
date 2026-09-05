"""
Commandes transverses : aide, historique, repetition, sortie.
"""

from __future__ import annotations

from core.context import CommandContext, Response
from core.registry import by_category, command


@command(
    name="help",
    patterns=[
        r"^(?:aide|help|aide\s+moi|commandes?|menu)$",
        r"(?:que|qu\s+est\s+ce\s+que)\s+(?:tu\s+)?(?:peux|sais)\s+(?:tu\s+)?faire",
        r"(?:liste|montre|affiche)\s+(?:moi\s+)?(?:les\s+|tes\s+)?commandes",
        r"^what\s+can\s+you\s+do",
    ],
    keywords=[["aide"], ["help"]],
    category="Divers",
    description="Afficher la liste des commandes disponibles",
    examples=["aide", "que peux-tu faire"],
    priority=95,
)
def show_help(ctx: CommandContext) -> Response:
    """Affiche toutes les commandes, groupees par catégorie."""
    lines = ["Voici ce que je sais faire :", ""]
    for category, commands in sorted(by_category().items()):
        lines.append("[" + category + "]")
        for cmd in commands:
            example = cmd.examples[0] if cmd.examples else ""
            suffix = ("   ex: " + example) if example else ""
            lines.append("  - " + (cmd.description or cmd.name) + suffix)
        lines.append("")
    lines.append("Astuce : vous pouvez commencer vos phrases par « Alma, ... ».")
    text = "\n".join(lines)
    # On affiche tout, mais on ne lit a voix haute qu un résumé.
    ctx.assistant.io.write(text)
    total = sum(len(c) for c in by_category().values())
    return Response(
        text="Je connais " + str(total) + " commandes, la liste complète est affichée ci-dessus.",
        speak=True,
    )


@command(
    name="repeat_last",
    patterns=[r"^(?:repete|repeter|refais|encore|again|recommence)\s*(?:la\s+derniere\s+commande)?$"],
    category="Divers",
    description="Répéter la dernière commande",
    examples=["repete", "refais"],
    priority=95,
)
def repeat_last(ctx: CommandContext) -> Response:
    """Rejoue la dernière commande executee."""
    last = ctx.assistant.last_command_text
    if not last:
        return Response(text="Je n'ai pas encore de commande à répéter.")
    ctx.assistant.io.write("(je rejoue : " + last + ")")
    return ctx.assistant.handle(last, source=ctx.source)


@command(
    name="history",
    patterns=[
        r"(?:qu\s+est\s+ce\s+que\s+je\s+t\s+ai\s+demande|historique|mes\s+dernieres\s+commandes)",
        r"^history$",
    ],
    keywords=[["historique"]],
    category="Divers",
    description="Voir les commandes demandées aujourd'hui",
    examples=["qu est-ce que je t ai demande aujourd'hui", "historique"],
    priority=90,
)
def history(ctx: CommandContext) -> Response:
    """Affiche l'historique du jour."""
    items = ctx.storage.history_today()
    # On ignore la demande d historique elle-meme.
    items = [i for i in items if i.get("command") != "history"]
    if not items:
        return Response(text="Vous ne m'avez encore rien demande aujourd'hui.")
    lines = ["Vos " + str(min(len(items), 15)) + " dernières demandes :"]
    for item in items[-15:]:
        heure = str(item.get("at", ""))[11:16]
        lines.append("  " + heure + "  " + str(item.get("text", "")))
    ctx.assistant.io.write("\n".join(lines))
    return Response(
        text="Vous m'avez fait " + str(len(items)) + " demandes aujourd'hui.", speak=True
    )


@command(
    name="clear_history",
    patterns=[r"(?:efface|effacer|vide|supprime)\s+(?:l\s+)?historique"],
    category="Divers",
    description="Effacer l'historique des commandes",
    examples=["efface l'historique"],
    priority=93,
)
def clear_history(ctx: CommandContext) -> Response:
    """Efface l'historique apres confirmation."""
    if not ctx.confirm("Effacer tout l'historique des commandes ?"):
        return Response(text="Historique conservé.")
    count = ctx.storage.history.clear()
    return Response(text="Historique effacé (" + str(count) + " entrées).")


@command(
    name="exit",
    # "quitte" et "stop" sont ancres en fin de phrase : sans cela,
    # "quitte Spotify" fermerait Alma au lieu de fermer Spotify.
    # "salut Alma" reste une salutation, pas un adieu.
    patterns=[
        r"^(?:au\s+revoir|a\s+bientot|adieu|bye|goodbye)\b",
        r"^(?:quitte|quitter|exit|stop|ferme\s+toi|arrete\s+toi)\s*(?:alma)?$",
        r"^(?:ciao|bonne\s+nuit)\s+alma$",
    ],
    keywords=[["quitte"], ["exit"]],
    category="Divers",
    description="Quitter Alma",
    examples=["au revoir Alma", "quitte"],
    priority=96,
)
def exit_alma(ctx: CommandContext) -> Response:
    """Termine proprement la session."""
    return Response(text="Au revoir. À votre service quand vous voulez.", should_exit=True)
