"""
Commandes transverses : aide, historique, repetition, sortie.
"""

from __future__ import annotations

from core.context import CommandContext, Response
from core.registry import by_category, command


@command(
    name="help",
    informatif=True,
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
    anglais = ctx.lang == "en"
    lines = ["Here's what I can do:" if anglais else "Voici ce que je sais faire :", ""]
    for category, commands in sorted(by_category().items()):
        lines.append("[" + category + "]")
        for cmd in commands:
            example = cmd.examples[0] if cmd.examples else ""
            suffix = ("   ex: " + example) if example else ""
            lines.append("  - " + (cmd.description or cmd.name) + suffix)
        lines.append("")
    lines.append("Tip: you can start any sentence with \"Alma, ...\"." if anglais
                 else "Astuce : vous pouvez commencer vos phrases par « Alma, ... ».")
    text = "\n".join(lines)
    # On affiche tout, mais on ne lit a voix haute qu un résumé.
    ctx.assistant.io.write(text)
    total = str(sum(len(c) for c in by_category().values()))
    return ctx.reponse(
        "Je connais " + total + " commandes, la liste complète est affichée ci-dessus.",
        "I know " + total + " commands; the full list is shown above.",
    )


@command(
    name="repeat_last",
    informatif=True,
    patterns=[r"^(?:repete|repeter|refais|encore|again|recommence)\s*(?:la\s+derniere\s+commande)?$"],
    category="Divers",
    description="Répéter la dernière commande",
    examples=["repete", "refais", "again"],
    priority=95,
)
def repeat_last(ctx: CommandContext) -> Response:
    """Rejoue la dernière commande executee."""
    last = ctx.assistant.last_command_text
    if not last:
        return ctx.reponse("Je n'ai pas encore de commande à répéter.",
                           "I don't have a command to repeat yet.")
    ctx.assistant.io.write("(je rejoue : " + last + ")")
    return ctx.assistant.handle(last, source=ctx.source)


@command(
    name="history",
    informatif=True,
    patterns=[
        r"(?:qu\s+est\s+ce\s+que\s+je\s+t\s+ai\s+demande|historique|mes\s+dernieres\s+commandes)",
        r"^history$",
    ],
    keywords=[["historique"]],
    category="Divers",
    description="Voir les commandes demandées aujourd'hui",
    examples=["qu est-ce que je t ai demande aujourd'hui", "historique", "history"],
    priority=90,
)
def history(ctx: CommandContext) -> Response:
    """Affiche l'historique du jour."""
    items = ctx.storage.history_today()
    # On ignore la demande d historique elle-meme.
    items = [i for i in items if i.get("command") != "history"]
    if not items:
        return ctx.reponse("Vous ne m'avez encore rien demande aujourd'hui.",
                           "You haven't asked me anything yet today.")
    combien = str(min(len(items), 15))
    lines = [(combien + " most recent requests:") if ctx.lang == "en"
             else ("Vos " + combien + " dernières demandes :")]
    for item in items[-15:]:
        heure = str(item.get("at", ""))[11:16]
        lines.append("  " + heure + "  " + str(item.get("text", "")))
    ctx.assistant.io.write("\n".join(lines))
    total = str(len(items))
    return ctx.reponse("Vous m'avez fait " + total + " demandes aujourd'hui.",
                       "You've made " + total + " requests today.")


@command(
    name="clear_history",
    patterns=[r"(?:efface|effacer|vide|supprime)\s+(?:l\s+)?historique",
              r"(?:clear|delete)\s+(?:the\s+)?history"],
    category="Divers",
    description="Effacer l'historique des commandes",
    examples=["efface l'historique", "clear history"],
    priority=93,
)
def clear_history(ctx: CommandContext) -> Response:
    """Efface l'historique apres confirmation."""
    if not ctx.confirm("Effacer tout l'historique des commandes ?"):
        return ctx.reponse("Historique conservé.", "History kept.")
    count = str(ctx.storage.history.clear())
    return ctx.reponse("Historique effacé (" + count + " entrées).",
                       "History cleared (" + count + " entries).")


@command(
    name="exit",
    informatif=True,
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
    adieu = ctx.reponse("Au revoir. À votre service quand vous voulez.",
                        "Goodbye. At your service whenever you need me.")
    adieu.should_exit = True
    return adieu
