from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from where_to_go.settings import LlmProvider

DATABASE_FILE = "where-to-go.sqlite3"


class ActiveProvider:
    """The reader a data folder has chosen, read without the app: the database is opened read-only and anything
    unreadable means the default."""

    KEY = "llm_provider"

    @classmethod
    def of(cls, data_dir: Path) -> LlmProvider:
        database = data_dir / DATABASE_FILE
        if not database.is_file():
            return LlmProvider.CLAUDE
        try:
            with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True) as connection:
                row = connection.execute("SELECT value FROM settings WHERE key = ?", (cls.KEY,)).fetchone()
            return LlmProvider(json.loads(row[0])) if row else LlmProvider.CLAUDE
        except (sqlite3.Error, ValueError, TypeError):
            return LlmProvider.CLAUDE
