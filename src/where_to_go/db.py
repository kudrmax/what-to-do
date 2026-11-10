from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from sqlalchemy import event as sa_event
from sqlalchemy.engine import Connection, Engine
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
        self._transaction: ContextVar[Connection | None] = ContextVar(f"transaction of {path}", default=None)
        sa_event.listen(self.engine, "connect", _sqlite_pragmas)
        SQLModel.metadata.create_all(self.engine)
        self._add_new_columns()

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Inside a transaction a session's commit only stages its changes; the transaction commits them all."""
        connection = self._transaction.get()
        if connection is None:
            with Session(self.engine, expire_on_commit=False) as session:
                yield session
        else:
            with Session(bind=connection, expire_on_commit=False, join_transaction_mode="rollback_only") as session:
                yield session

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Everything written inside is saved together or not at all, even if the process dies halfway.

        Never wait for Claude or the network inside: SQLite lets one writer at a time, everyone else waits.
        """
        if self._transaction.get() is not None:
            yield
            return
        with self.engine.begin() as connection:
            token = self._transaction.set(connection)
            try:
                yield
            finally:
                self._transaction.reset(token)

    def close(self) -> None:
        self.engine.dispose()

    def _add_new_columns(self) -> None:
        """create_all makes missing tables only; a nullable column added to a model is added to its existing table here."""
        with self.engine.begin() as connection:
            for table in SQLModel.metadata.sorted_tables:
                present = {row[1] for row in connection.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
                for column in table.columns:
                    if column.name in present:
                        continue
                    if not column.nullable:
                        raise RuntimeError(f"{table.name}.{column.name} is new and required: it needs a migration")
                    kind = column.type.compile(dialect=self.engine.dialect)
                    connection.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}')


def _sqlite_pragmas(connection, _record) -> None:
    cursor = connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()
