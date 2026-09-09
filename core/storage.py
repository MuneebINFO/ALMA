"""
Stockage local simple en JSON (notes, rappels, historique).

Pas de base de donnees : un fichier JSON par collection, ecrit de facon
atomique pour ne jamais corrompre les donnees en cas d interruption.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path


class JsonCollection:
    """Une liste d enregistrements persistee dans un fichier JSON."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, items: list) -> None:
        """Écriture atomique : fichier temporaire puis remplacement."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(items, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def append(self, item: dict) -> dict:
        items = self.load()
        item.setdefault("id", (max([i.get("id", 0) for i in items], default=0)) + 1)
        item.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
        items.append(item)
        self.save(items)
        return item

    def remove(self, item_id: int) -> bool:
        items = self.load()
        remaining = [i for i in items if i.get("id") != item_id]
        if len(remaining) == len(items):
            return False
        self.save(remaining)
        return True

    def clear(self) -> int:
        count = len(self.load())
        self.save([])
        return count

    def __len__(self) -> int:
        return len(self.load())


class Storage:
    """Regroupe les collections utilisees par Alma."""

    def __init__(self, config) -> None:
        self.config = config
        self.notes = JsonCollection(config.resolve_path("notes", "data/notes.json"))
        self.reminders = JsonCollection(config.resolve_path("reminders", "data/reminders.json"))
        self.history = JsonCollection(config.resolve_path("history", "data/history.json"))
        # Ce qu Alma retient d une session a l autre : preferences, proches,
        # projets. A distinguer des notes, qui sont des pense-betes dates, et
        # du contexte de session, qui expire au bout d une minute.
        self.souvenirs = JsonCollection(
            config.resolve_path("memory", "data/souvenirs.json"))

    def log_command(self, text: str, command_name: str, source: str, response: str = "") -> None:
        """Journalise une commande executee (limite aux 500 dernières)."""
        items = self.history.load()
        items.append(
            {
                "id": (max([i.get("id", 0) for i in items], default=0)) + 1,
                "at": datetime.now().isoformat(timespec="seconds"),
                "text": text,
                "command": command_name,
                "source": source,
                "response": response[:300],
            }
        )
        self.history.save(items[-500:])

    def history_today(self) -> list:
        today = datetime.now().date().isoformat()
        return [i for i in self.history.load() if str(i.get("at", "")).startswith(today)]
