from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cities (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    timezone TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    kind TEXT NOT NULL,
    handle TEXT NOT NULL,
    title TEXT NOT NULL,
    last_refreshed_at TEXT,
    last_error TEXT,
    last_post_id INTEGER,
    events_found INTEGER NOT NULL DEFAULT 0,
    UNIQUE (kind, handle, city_id)
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    external_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    published_at TEXT NOT NULL,
    text TEXT NOT NULL,
    image_paths TEXT NOT NULL DEFAULT '[]',
    processed_at TEXT,
    process_error TEXT,
    UNIQUE (source_id, external_id)
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    position INTEGER NOT NULL,
    is_fallback INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    original_title TEXT NOT NULL,
    description TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    start_time TEXT,
    rrule TEXT,
    venue TEXT,
    address TEXT,
    price TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    image_path TEXT,
    is_cancelled INTEGER NOT NULL DEFAULT 0,
    conflicts TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS mentions (
    id INTEGER PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
    item_index INTEGER NOT NULL,
    data TEXT NOT NULL,
    locked INTEGER NOT NULL DEFAULT 0,
    UNIQUE (post_id, item_index)
);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY,
    city_id INTEGER NOT NULL REFERENCES cities(id),
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    address TEXT,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marks (
    event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    interest INTEGER,
    plan TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS events_city_date ON events (city_id, start_date);
CREATE INDEX IF NOT EXISTS mentions_event ON mentions (event_id);
CREATE INDEX IF NOT EXISTS posts_unprocessed ON posts (processed_at);
"""


class Database:
    """One SQLite file shared by all repositories; writes are serialized."""

    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.RLock()
        self._depth = 0

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            outermost = self._depth == 0
            if outermost:
                self._conn.execute("BEGIN")
            self._depth += 1
            try:
                yield self._conn
            except BaseException:
                self._depth -= 1
                if outermost:
                    self._conn.execute("ROLLBACK")
                raise
            self._depth -= 1
            if outermost:
                self._conn.execute("COMMIT")

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        with self.transaction() as conn:
            return conn.execute(sql, params).lastrowid or 0

    def close(self) -> None:
        self._conn.close()
