from __future__ import annotations

import contextlib
import json
import sqlite3
from pathlib import Path

from where_to_go.db import DATABASE_FILE
from where_to_go.settings import AppSettings, LlmProvider


class ActiveProvider:
    """The reader a data folder has chosen, read without the app: the database is opened read-only and anything
    unreadable means the default."""

    FIELD = "llm_provider"

    @classmethod
    def of(cls, data_dir: Path) -> LlmProvider:
        default = AppSettings.model_fields[cls.FIELD].default
        database = data_dir / DATABASE_FILE
        if not database.is_file():
            return default
        try:
            with contextlib.closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as connection:
                row = connection.execute("SELECT value FROM settings WHERE key = ?", (cls.FIELD,)).fetchone()
            return AppSettings.model_validate({cls.FIELD: json.loads(row[0])}).llm_provider if row else default
        except (sqlite3.Error, ValueError, TypeError):
            return default
