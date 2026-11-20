from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlmodel import select

from where_to_go.db import Database
from where_to_go.models import Setting
from where_to_go.phone_page.secrets import MemorySecret, SecretStore, SecretStoreError

log = logging.getLogger(__name__)


class PhonePageConfig(BaseModel):
    enabled: bool = False
    repository: str = ""
    token: str = ""
    password: str = ""
    salt: str = ""
    published_hash: str = ""
    published_at: datetime | None = None
    last_error: str | None = None
    page_url: str = ""

    @property
    def active(self) -> bool:
        """On, and holding a token of this installation: a copy of the data has the flag but never the token."""
        return self.enabled and bool(self.token)


class PhonePageConfigRepository:
    """Keeps the phone page settings in the settings table, apart from AppSettings, and the GitHub token outside
    the data folder, in a secret store of this installation."""

    PREFIX = "phone_page."
    TOKEN = "token"

    def __init__(self, db: Database, token: SecretStore | None = None) -> None:
        self._db = db
        self._token = token or MemorySecret()
        self._cached_token: str | None = None

    def load(self) -> PhonePageConfig:
        with self._db.session() as s:
            rows = s.exec(select(Setting).where(Setting.key.startswith(self.PREFIX)))
            stored = {row.key.removeprefix(self.PREFIX): row.value for row in rows if row.key != self.PREFIX + self.TOKEN}
        return PhonePageConfig.model_validate({**stored, self.TOKEN: self._read_token()})

    def update(self, **change: Any) -> PhonePageConfig:
        updated = PhonePageConfig.model_validate({**self.load().model_dump(), **change})
        if self.TOKEN in change:
            self._write_token(updated.token)
        dumped = updated.model_dump(mode="json")
        with self._db.session() as s:
            for key in change:
                if key != self.TOKEN:
                    s.merge(Setting(key=self.PREFIX + key, value=dumped[key]))
            s.commit()
        return updated

    def adopt_legacy_token(self, owner: bool) -> None:
        """Before 1.28 the token sat in the settings table and travelled with every copy of the data. The installation
        that owns the data folder moves it to its secret store; any other instance, a copy, drops it unused."""
        key = self.PREFIX + self.TOKEN
        with self._db.session() as s:
            row = s.get(Setting, key)
            legacy = row.value if row is not None else None
        if legacy is None:
            return
        if owner and legacy and not self._read_token():
            try:
                self._write_token(str(legacy))
            except SecretStoreError:
                log.exception("Moving the phone page token to the keychain failed; it stays in the database until the next start")
                return
        with self._db.session() as s:
            row = s.get(Setting, key)
            if row is not None:
                s.delete(row)
                s.commit()

    def _read_token(self) -> str:
        if self._cached_token is None:
            try:
                self._cached_token = self._token.read()
            except SecretStoreError:
                log.exception("Reading the phone page token failed")
                return ""
        return self._cached_token

    def _write_token(self, token: str) -> None:
        self._token.write(token)
        self._cached_token = token
