"""Append-only record of every product made, so we never repeat ourselves."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[dict] = json.loads(path.read_text()) if path.exists() else []

    def titles(self) -> list[str]:
        return [e["title"] for e in self.entries]

    def slugs(self) -> set[str]:
        return {e["slug"] for e in self.entries}

    def add(self, entry: dict) -> None:
        self.entries.append({"created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, indent=2) + "\n")
