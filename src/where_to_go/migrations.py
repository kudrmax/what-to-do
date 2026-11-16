"""Data a new column needs from the data already there, run once, in the transaction that adds the column."""

from __future__ import annotations

import json
from collections.abc import Callable

from sqlalchemy.engine import Connection

from where_to_go.reading_rules import ReadingRules

LEGACY_CARD_LANGUAGE = "русский"
"""What every install described events in before the language became a setting of the city (1.16)."""


def _card_language_from_settings(connection: Connection) -> None:
    """The one global language becomes each city's own. The posts already read were read in it, so their fingerprint
    says so and nothing is read again."""
    stored = connection.exec_driver_sql("SELECT value FROM settings WHERE key = 'description_language'").scalar()
    language = (json.loads(stored) if stored else None) or LEGACY_CARD_LANGUAGE
    connection.exec_driver_sql("UPDATE cities SET card_language = ?", (language,))
    connection.exec_driver_sql(
        "UPDATE posts SET read_with = read_with || ? WHERE read_with IS NOT NULL",
        (ReadingRules.language_part(language),),
    )


AFTER_NEW_COLUMN: dict[str, Callable[[Connection], None]] = {
    "cities.card_language": _card_language_from_settings,
}
