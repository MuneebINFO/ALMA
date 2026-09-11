"""
Planificateur de rappels et de minuteurs.

Repose sur threading.Timer (aucune dependance externe). Les rappels sont
persistes en JSON : ceux qui sont encore valides sont replanifies au demarrage,
ceux qui ont expire pendant que Alma etait eteint sont signales une fois.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from core import win_utils

log = logging.getLogger(__name__)


class Scheduler:
    """Gere les rappels actifs de la session."""

    def __init__(self, assistant) -> None:
        self.assistant = assistant
        self._timers: dict = {}
        self._lock = threading.Lock()

    # -- planification --------------------------------------------------------
    def schedule(self, label: str, due: datetime, kind: str = "rappel") -> dict:
        """Enregistre puis arme un rappel."""
        item = self.assistant.storage.reminders.append(
            {
                "label": label,
                "due": due.isoformat(timespec="seconds"),
                "kind": kind,
                "done": False,
            }
        )
        self._arm(item)
        return item

    def _arm(self, item: dict) -> None:
        """Arme un timer pour un rappel deja persiste."""
        try:
            due = datetime.fromisoformat(str(item.get("due")))
        except (TypeError, ValueError):
            return
        delay = max(0.0, (due - datetime.now()).total_seconds())
        timer = threading.Timer(delay, self._fire, args=(item.get("id"),))
        timer.daemon = True
        with self._lock:
            self._timers[item.get("id")] = timer
        timer.start()

    def _fire(self, item_id) -> None:
        """Declenche un rappel : notification + son + lecture vocale."""
        items = self.assistant.storage.reminders.load()
        item = next((i for i in items if i.get("id") == item_id), None)
        if item is None or item.get("done"):
            return
        item["done"] = True
        self.assistant.storage.reminders.save(items)
        with self._lock:
            self._timers.pop(item_id, None)

        label = str(item.get("label") or "")
        kind = str(item.get("kind") or "rappel")
        message = ("Minuteur termine" if kind == "minuteur" else "Rappel") + (
            (" : " + label) if label else ""
        )
        try:
            win_utils.notify(
                self.assistant.name,
                message,
                popup=bool(self.assistant.config.get("notifications.popup", True)),
                sound=bool(self.assistant.config.get("notifications.sound", True)),
            )
            self.assistant.emit(message)
        except Exception as exc:
            log.debug("Notification impossible : %s", exc)

    # -- cycle de vie ---------------------------------------------------------
    def restore(self) -> list:
        """
        Replanifie les rappels en attente au demarrage.
        Retourne la liste de ceux qui ont expire pendant l arret.
        """
        items = self.assistant.storage.reminders.load()
        missed = []
        changed = False
        now = datetime.now()
        for item in items:
            if item.get("done"):
                continue
            try:
                due = datetime.fromisoformat(str(item.get("due")))
            except (TypeError, ValueError):
                item["done"] = True
                changed = True
                continue
            if due <= now:
                item["done"] = True
                changed = True
                missed.append(item)
            else:
                self._arm(item)
        if changed:
            self.assistant.storage.reminders.save(items)
        return missed

    def pending(self) -> list:
        """Rappels encore en attente, tries par echeance."""
        items = [i for i in self.assistant.storage.reminders.load() if not i.get("done")]
        return sorted(items, key=lambda i: str(i.get("due", "")))

    def cancel_all(self) -> int:
        """Annule tous les rappels en attente."""
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        items = self.assistant.storage.reminders.load()
        count = 0
        for item in items:
            if not item.get("done"):
                item["done"] = True
                count += 1
        self.assistant.storage.reminders.save(items)
        return count

    def shutdown(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()


def parse_duration(tokens: list) -> timedelta | None:
    """
    Extrait une duree depuis des mots : "10 minutes", "1 heure", "30 secondes".
    Retourne None si aucune duree n est trouvee.
    """
    units = {
        "seconde": 1, "secondes": 1, "sec": 1, "s": 1,
        "minute": 60, "minutes": 60, "min": 60, "mn": 60,
        "heure": 3600, "heures": 3600, "h": 3600,
        "jour": 86400, "jours": 86400,
        # Memes unites, en anglais.
        "second": 1, "seconds": 1,
        "mins": 60,
        "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
        "day": 86400, "days": 86400,
    }
    words = {"une": 1, "un": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
             "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "quinze": 15,
             "vingt": 20, "trente": 30, "demi": 0.5,
             # Memes nombres, en anglais.
             "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
             "thirty": 30, "half": 0.5}
    total = 0.0
    found = False
    for index, token in enumerate(tokens):
        if token not in units:
            continue
        amount = 1.0
        if index > 0:
            previous = tokens[index - 1]
            if previous.isdigit():
                amount = float(previous)
            elif previous in words:
                amount = float(words[previous])
        total += amount * units[token]
        found = True
    return timedelta(seconds=total) if found and total > 0 else None
