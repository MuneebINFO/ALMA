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
        r"^note\s*(?:that|:)?\s*(.+)$",
        r"^(?:take|add|create)\s+(?:a\s+)?notes?\s*(?::|that)?\s*(.+)$",
    ],
    category="Productivité",
    description="Prendre une note horodatée",
    examples=["note que je dois rappeler ma banque demain",
              "note that I need to call my bank tomorrow"],
    priority=85,
)
def add_note(ctx: CommandContext) -> Response:
    """Ajoute une note dans data/notes.json."""
    content = ctx.arg
    if not content:
        return ctx.erreur("Que dois-je noter ?", "What should I note down?")
    ctx.storage.notes.append({"text": content, "source": ctx.source})
    return ctx.reponse("C'est noté : " + content, "Noted: " + content)


@command(
    name="read_notes",
    informatif=True,
    patterns=[
        r"(?:lis|lire|montre|affiche|liste|donne)\s*(?:moi)?\s*(?:mes|les)?\s*notes",
        r"^(?:mes\s+notes|notes)$",
        r"(?:qu\s+est\s+ce\s+que\s+j\s+ai\s+note)",
        r"(?:read|show|list)\s*(?:me)?\s*(?:my\s+)?notes",
        r"^my\s+notes$",
    ],
    keywords=[["lis", "notes"], ["mes", "notes"], ["my", "notes"]],
    category="Productivité",
    description="Relire les notes enregistrées",
    examples=["lis mes notes", "read my notes"],
    priority=90,
)
def read_notes(ctx: CommandContext) -> Response:
    """Affiche les notes et lit les plus recentes a voix haute."""
    notes = ctx.storage.notes.load()
    if not notes:
        return ctx.reponse("Vous n'avez aucune note enregistrée.",
                           "You don't have any notes saved.")
    anglais = ctx.lang == "en"
    lines = [("Your notes (" + str(len(notes)) + "):") if anglais
             else ("Vos notes (" + str(len(notes)) + ") :")]
    for note in notes:
        date = str(note.get("created_at", ""))[:16].replace("T", " ")
        lines.append("  #" + str(note.get("id")) + "  [" + date + "]  " + str(note.get("text", "")))
    ctx.assistant.io.write("\n".join(lines))

    latest = notes[-3:]
    spoken = " ; ".join(str(n.get("text", "")) for n in latest)
    recentes = len(notes) > 3
    prefix = (("Here are your latest notes: " if recentes else "Your notes: ") if anglais
              else ("Voici vos dernières notes : " if recentes else "Vos notes : "))
    return Response(text=prefix + spoken)


@command(
    name="delete_note",
    patterns=[r"(?:supprime|supprimer|efface|effacer|retire)\s+(?:la\s+)?notes?\s*(?:numero\s*)?(\d+)",
              r"(?:delete|remove)\s+notes?\s*(?:number\s*|#\s*)?(\d+)"],
    category="Productivité",
    description="Supprimer une note par son numéro",
    examples=["supprime la note 2", "delete note 2"],
    priority=92,
)
def delete_note(ctx: CommandContext) -> Response:
    """Supprime une note précise."""
    note_id = int(ctx.arg or 0)
    if ctx.storage.notes.remove(note_id):
        return ctx.reponse("Note " + str(note_id) + " supprimée.",
                           "Note " + str(note_id) + " deleted.")
    return ctx.erreur("Je n'ai pas trouvé de note numéro " + str(note_id) + ".",
                      "I couldn't find a note numbered " + str(note_id) + ".")


@command(
    name="clear_notes",
    patterns=[r"(?:supprime|efface|vide)\s+(?:toutes\s+)?(?:mes|les)\s+notes",
              r"(?:delete|clear)\s+(?:all\s+)?(?:my\s+)?notes"],
    category="Productivité",
    description="Supprimer toutes les notes",
    examples=["efface toutes mes notes", "clear all my notes"],
    priority=93,
)
def clear_notes(ctx: CommandContext) -> Response:
    """Vide le carnet de notes apres confirmation."""
    if not ctx.confirm("Supprimer definitivement toutes vos notes ?",
                       "Delete all your notes for good?"):
        return ctx.reponse("Vos notes sont conservées.", "Your notes are kept.")
    count = ctx.storage.notes.clear()
    return ctx.reponse(str(count) + " notes supprimées.",
                       str(count) + " notes deleted.")


@command(
    name="set_reminder",
    patterns=[
        r"^(?:rappelle|rappeler)\s*(?:moi)?\s+(?:dans|d\s+ici)\s+.+?\s+(?:de|que|d)\s+(.+)$",
        r"^(?:rappelle|rappeler)\s*(?:moi)?\s+(.+?)\s+dans\s+\d+.*$",
        r"^remind\s+me\s+in\s+.+?\s+to\s+(.+)$",
        r"^remind\s+me\s+to\s+(.+?)\s+in\s+\d+.*$",
    ],
    category="Productivité",
    description="Programmer un rappel (notification + son)",
    examples=["rappelle-moi dans 10 minutes de sortir le gateau",
              "remind me in 10 minutes to take out the cake"],
    priority=94,
)
def set_reminder(ctx: CommandContext) -> Response:
    """Programme un rappel avec un libelle."""
    label = ctx.arg
    duration = parse_duration(ctx.tokens)
    if duration is None:
        return ctx.erreur(
            "Je n'ai pas compris le délai. Essayez : rappelle-moi dans 10 minutes de ...",
            "I didn't catch the delay. Try: \"remind me in 10 minutes to ...\"",
        )
    due = datetime.now() + duration
    ctx.assistant.scheduler.schedule(label, due, kind="rappel")
    return ctx.reponse(
        "Rappel programmé pour " + due.strftime("%H:%M") + " : " + label + ".",
        "Reminder set for " + due.strftime("%I:%M %p").lstrip("0") + ": " + label + ".",
    )


@command(
    name="set_timer",
    patterns=[
        r"(?:lance|lancer|demarre|met|mets|programme)\s+(?:un\s+)?(?:minuteur|timer|chrono|compte\s+a\s+rebours)",
        r"^(?:minuteur|timer)\s+(?:de\s+)?\d+",
        r"(?:start|set)\s+(?:a\s+)?(?:timer|countdown)",
        r"^timer\s+(?:for\s+)?\d+",
    ],
    keywords=[["minuteur"], ["timer"]],
    category="Productivité",
    description="Lancer un minuteur",
    examples=["lance un minuteur de 5 minutes", "start a timer for 5 minutes"],
    priority=94,
)
def set_timer(ctx: CommandContext) -> Response:
    """Lance un minuteur simple."""
    duration = parse_duration(ctx.tokens)
    if duration is None:
        return ctx.erreur(
            "Quelle durée ? Exemple : lance un minuteur de 5 minutes.",
            'How long? For example: "start a timer for 5 minutes".',
        )
    due = datetime.now() + duration
    minutes = duration.total_seconds() / 60
    label = ("%g minute" % minutes) + ("s" if minutes >= 2 else "")
    ctx.assistant.scheduler.schedule(label, due, kind="minuteur")
    return ctx.reponse(
        "Minuteur de " + label + " lancé. Fin à " + due.strftime("%H:%M") + ".",
        label.capitalize() + " timer started. Ends at "
        + due.strftime("%I:%M %p").lstrip("0") + ".",
    )


@command(
    name="list_reminders",
    informatif=True,
    patterns=[
        r"(?:liste|montre|affiche|quels?\s+sont)\s*(?:moi)?\s*(?:mes|les)\s+(?:rappels|minuteurs|alarmes)",
        r"^(?:mes\s+rappels|rappels)$",
        r"(?:list|show)\s*(?:me)?\s*(?:my\s+)?(?:reminders|timers|alarms)",
        r"^my\s+reminders$",
    ],
    category="Productivité",
    description="Lister les rappels en attente",
    examples=["mes rappels", "my reminders"],
    priority=92,
)
def list_reminders(ctx: CommandContext) -> Response:
    """Affiche les rappels encore actifs."""
    pending = ctx.assistant.scheduler.pending()
    if not pending:
        return ctx.reponse("Aucun rappel en attente.", "No reminders pending.")
    lines = ["Pending reminders:" if ctx.lang == "en" else "Rappels en attente :"]
    for item in pending:
        heure = str(item.get("due", ""))[11:16]
        lines.append("  " + heure + "  " + str(item.get("label", "")))
    ctx.assistant.io.write("\n".join(lines))
    return ctx.reponse("Vous avez " + str(len(pending)) + " rappel en attente.",
                       "You have " + str(len(pending)) + " reminder(s) pending.")


@command(
    name="cancel_reminders",
    patterns=[r"(?:annule|annuler|supprime|arrete)\s+(?:tous\s+)?(?:mes|les)\s+(?:rappels|minuteurs)",
              r"(?:cancel|clear)\s+(?:all\s+)?(?:my\s+)?(?:reminders|timers)"],
    category="Productivité",
    description="Annuler tous les rappels",
    examples=["annule mes rappels", "cancel all my reminders"],
    priority=95,
)
def cancel_reminders(ctx: CommandContext) -> Response:
    """Annule tous les rappels en attente."""
    count = ctx.assistant.scheduler.cancel_all()
    return ctx.reponse(str(count) + " rappel annulé.",
                       str(count) + " reminder(s) cancelled.")


@command(
    name="read_clipboard",
    informatif=True,
    patterns=[
        r"(?:lis|lire|montre|affiche|donne)\s*(?:moi)?\s*(?:le\s+)?presse\s*papiers?",
        r"qu\s+est\s+ce\s+qu\s+il\s+y\s+a\s+dans\s+le\s+presse\s*papiers?",
        r"(?:read|show)\s*(?:me)?\s*(?:the\s+)?clipboard",
        r"what\s+s\s+in\s+the\s+clipboard",
    ],
    keywords=[["lis", "presse papiers"], ["read", "clipboard"]],
    category="Productivité",
    description="Lire le contenu du presse-papiers",
    examples=["lis le presse-papiers", "read the clipboard"],
    priority=90,
)
def read_clipboard(ctx: CommandContext) -> Response:
    """Lit le presse-papiers."""
    content = win_utils.get_clipboard()
    if not content.strip():
        return ctx.reponse("Le presse-papiers est vide.", "The clipboard is empty.")
    ctx.assistant.io.write("Presse-papiers :\n" + content)
    preview = content.strip().replace("\n", " ")[:200]
    return ctx.reponse("Le presse-papiers contient : " + preview,
                       "The clipboard contains: " + preview)


@command(
    name="write_clipboard",
    patterns=[
        r"^(?:copie|copier)\s+(.+?)\s+dans\s+le\s+presse\s*papiers?$",
        r"^(?:copie|copier)\s+(.+)$",
        r"^copy\s+(.+?)\s+to\s+(?:the\s+)?clipboard$",
    ],
    category="Productivité",
    description="Copier un texte dans le presse-papiers",
    examples=["copie bonjour tout le monde dans le presse-papiers",
              "copy hello world to the clipboard"],
    priority=84,
)
def write_clipboard(ctx: CommandContext) -> Response:
    """Ecrit un texte dans le presse-papiers."""
    content = ctx.arg
    if not content:
        return ctx.erreur("Que dois-je copier ?", "What should I copy?")
    if win_utils.set_clipboard(content):
        return ctx.reponse("Copié dans le presse-papiers : " + content,
                           "Copied to the clipboard: " + content)
    return ctx.erreur("Je n'ai pas pu écrire dans le presse-papiers.",
                      "I couldn't write to the clipboard.")
