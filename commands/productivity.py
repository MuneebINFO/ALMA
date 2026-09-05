"""
Productivité : notes, rappels, minuteurs, presse-papiers.
"""

from __future__ import annotations

from datetime import datetime

from core import win_utils
from core.context import CommandContext, Response
from core.registry import command
from core.scheduler import parse_duration


@command(
    name="add_note",
    patterns=[
        r"^(?:note|notes|noter)\s+(?:que|qu\s+il\s+faut|de|:)?\s*(.+)$",
        r"^(?:prends?|prendre|ajoute|ajouter|cree)\s+(?:une\s+)?notes?\s*(?::|que|de)?\s*(.+)$",
    ],
    category="Productivité",
    description="Prendre une note horodatée",
    examples=["note que je dois rappeler ma banque demain"],
    priority=85,
)
def add_note(ctx: CommandContext) -> Response:
    """Ajoute une note dans data/notes.json."""
    content = ctx.arg
    if not content:
        return Response.error("Que dois-je noter ?")
    ctx.storage.notes.append({"text": content, "source": ctx.source})
    return Response(text="C'est noté : " + content)


@command(
    name="read_notes",
    patterns=[
        r"(?:lis|lire|montre|affiche|liste|donne)\s*(?:moi)?\s*(?:mes|les)?\s*notes",
        r"^(?:mes\s+notes|notes)$",
        r"(?:qu\s+est\s+ce\s+que\s+j\s+ai\s+note)",
    ],
    keywords=[["lis", "notes"], ["mes", "notes"]],
    category="Productivité",
    description="Relire les notes enregistrées",
    examples=["lis mes notes"],
    priority=90,
)
def read_notes(ctx: CommandContext) -> Response:
    """Affiche les notes et lit les plus recentes a voix haute."""
    notes = ctx.storage.notes.load()
    if not notes:
        return Response(text="Vous n'avez aucune note enregistrée.")
    lines = ["Vos notes (" + str(len(notes)) + ") :"]
    for note in notes:
        date = str(note.get("created_at", ""))[:16].replace("T", " ")
        lines.append("  #" + str(note.get("id")) + "  [" + date + "]  " + str(note.get("text", "")))
    ctx.assistant.io.write("\n".join(lines))

    latest = notes[-3:]
    spoken = " ; ".join(str(n.get("text", "")) for n in latest)
    prefix = "Voici vos dernières notes : " if len(notes) > 3 else "Vos notes : "
    return Response(text=prefix + spoken)


@command(
    name="delete_note",
    patterns=[r"(?:supprime|supprimer|efface|effacer|retire)\s+(?:la\s+)?notes?\s*(?:numero\s*)?(\d+)"],
    category="Productivité",
    description="Supprimer une note par son numéro",
    examples=["supprime la note 2"],
    priority=92,
)
def delete_note(ctx: CommandContext) -> Response:
    """Supprime une note précise."""
    note_id = int(ctx.arg or 0)
    if ctx.storage.notes.remove(note_id):
        return Response(text="Note " + str(note_id) + " supprimée.")
    return Response.error("Je n'ai pas trouvé de note numéro " + str(note_id) + ".")


@command(
    name="clear_notes",
    patterns=[r"(?:supprime|efface|vide)\s+(?:toutes\s+)?(?:mes|les)\s+notes"],
    category="Productivité",
    description="Supprimer toutes les notes",
    examples=["efface toutes mes notes"],
    priority=93,
)
def clear_notes(ctx: CommandContext) -> Response:
    """Vide le carnet de notes apres confirmation."""
    if not ctx.confirm("Supprimer definitivement toutes vos notes ?"):
        return Response(text="Vos notes sont conservées.")
    count = ctx.storage.notes.clear()
    return Response(text=str(count) + " notes supprimées.")


@command(
    name="set_reminder",
    patterns=[
        r"^(?:rappelle|rappeler)\s*(?:moi)?\s+(?:dans|d\s+ici)\s+.+?\s+(?:de|que|d)\s+(.+)$",
        r"^(?:rappelle|rappeler)\s*(?:moi)?\s+(.+?)\s+dans\s+\d+.*$",
    ],
    category="Productivité",
    description="Programmer un rappel (notification + son)",
    examples=["rappelle-moi dans 10 minutes de sortir le gateau"],
    priority=94,
)
def set_reminder(ctx: CommandContext) -> Response:
    """Programme un rappel avec un libelle."""
    label = ctx.arg
    duration = parse_duration(ctx.tokens)
    if duration is None:
        return Response.error(
            "Je n'ai pas compris le délai. Essayez : rappelle-moi dans 10 minutes de ..."
        )
    due = datetime.now() + duration
    ctx.assistant.scheduler.schedule(label, due, kind="rappel")
    return Response(text="Rappel programmé pour " + due.strftime("%H:%M") + " : " + label + ".")


@command(
    name="set_timer",
    patterns=[
        r"(?:lance|lancer|demarre|met|mets|programme)\s+(?:un\s+)?(?:minuteur|timer|chrono|compte\s+a\s+rebours)",
        r"^(?:minuteur|timer)\s+(?:de\s+)?\d+",
    ],
    keywords=[["minuteur"], ["timer"]],
    category="Productivité",
    description="Lancer un minuteur",
    examples=["lance un minuteur de 5 minutes"],
    priority=94,
)
def set_timer(ctx: CommandContext) -> Response:
    """Lance un minuteur simple."""
    duration = parse_duration(ctx.tokens)
    if duration is None:
        return Response.error("Quelle durée ? Exemple : lance un minuteur de 5 minutes.")
    due = datetime.now() + duration
    minutes = duration.total_seconds() / 60
    label = ("%g minute" % minutes) + ("s" if minutes >= 2 else "")
    ctx.assistant.scheduler.schedule(label, due, kind="minuteur")
    return Response(text="Minuteur de " + label + " lancé. Fin à " + due.strftime("%H:%M") + ".")


@command(
    name="list_reminders",
    patterns=[
        r"(?:liste|montre|affiche|quels?\s+sont)\s*(?:moi)?\s*(?:mes|les)\s+(?:rappels|minuteurs|alarmes)",
        r"^(?:mes\s+rappels|rappels)$",
    ],
    category="Productivité",
    description="Lister les rappels en attente",
    examples=["mes rappels"],
    priority=92,
)
def list_reminders(ctx: CommandContext) -> Response:
    """Affiche les rappels encore actifs."""
    pending = ctx.assistant.scheduler.pending()
    if not pending:
        return Response(text="Aucun rappel en attente.")
    lines = ["Rappels en attente :"]
    for item in pending:
        heure = str(item.get("due", ""))[11:16]
        lines.append("  " + heure + "  " + str(item.get("label", "")))
    ctx.assistant.io.write("\n".join(lines))
    return Response(text="Vous avez " + str(len(pending)) + " rappel en attente.")


@command(
    name="cancel_reminders",
    patterns=[r"(?:annule|annuler|supprime|arrete)\s+(?:tous\s+)?(?:mes|les)\s+(?:rappels|minuteurs)"],
    category="Productivité",
    description="Annuler tous les rappels",
    examples=["annule mes rappels"],
    priority=95,
)
def cancel_reminders(ctx: CommandContext) -> Response:
    """Annule tous les rappels en attente."""
    count = ctx.assistant.scheduler.cancel_all()
    return Response(text=str(count) + " rappel annulé.")


@command(
    name="read_clipboard",
    patterns=[
        r"(?:lis|lire|montre|affiche|donne)\s*(?:moi)?\s*(?:le\s+)?presse\s*papiers?",
        r"qu\s+est\s+ce\s+qu\s+il\s+y\s+a\s+dans\s+le\s+presse\s*papiers?",
    ],
    keywords=[["lis", "presse papiers"]],
    category="Productivité",
    description="Lire le contenu du presse-papiers",
    examples=["lis le presse-papiers"],
    priority=90,
)
def read_clipboard(ctx: CommandContext) -> Response:
    """Lit le presse-papiers."""
    content = win_utils.get_clipboard()
    if not content.strip():
        return Response(text="Le presse-papiers est vide.")
    ctx.assistant.io.write("Presse-papiers :\n" + content)
    preview = content.strip().replace("\n", " ")[:200]
    return Response(text="Le presse-papiers contient : " + preview)


@command(
    name="write_clipboard",
    patterns=[
        r"^(?:copie|copier)\s+(.+?)\s+dans\s+le\s+presse\s*papiers?$",
        r"^(?:copie|copier)\s+(.+)$",
    ],
    category="Productivité",
    description="Copier un texte dans le presse-papiers",
    examples=["copie bonjour tout le monde dans le presse-papiers"],
    priority=84,
)
def write_clipboard(ctx: CommandContext) -> Response:
    """Ecrit un texte dans le presse-papiers."""
    content = ctx.arg
    if not content:
        return Response.error("Que dois-je copier ?")
    if win_utils.set_clipboard(content):
        return Response(text="Copié dans le presse-papiers : " + content)
    return Response.error("Je n'ai pas pu écrire dans le presse-papiers.")
