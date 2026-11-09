from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from where_to_go import models  # noqa: F401  (registers the tables)


class Database:
    """One SQLite file; the tables are the models."""

    def __init__(self, path: Path | str) -> None:
        options: dict = {"connect_args": {"check_same_thread": False, "timeout": 30}}
        if str(path) == ":memory:":
            url = "sqlite://"
            options["poolclass"] = StaticPool
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{path}"
        self.engine: Engine = create_engine(url, **options)
        sa_event.listen(self.engine, "connect", _sqlite_pragmas)
        SQLModel.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine, expire_on_commit=False) as session:
            yield session

    def close(self) -> None:
        self.engine.dispose()


def _sqlite_pragmas(connection, _record) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()
