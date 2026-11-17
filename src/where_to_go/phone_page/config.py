from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlmodel import select

from where_to_go.db import Database
from where_to_go.models import Setting


class PhonePageConfig(BaseModel):
    enabled: bool = False
    repository: str = ""
    token: str = ""
    password: str = ""
    salt: str = ""
    published_hash: str = ""
    published_at: datetime | None = None
    last_error: str | None = None


class PhonePageConfigRepository:
    """Keeps the phone page settings and secrets in the settings table, apart from AppSettings."""

    PREFIX = "phone_page."

    def __init__(self, db: Database) -> None:
        self._db = db

    def load(self) -> PhonePageConfig:
        with self._db.session() as s:
            rows = s.exec(select(Setting).where(Setting.key.startswith(self.PREFIX)))
            return PhonePageConfig.model_validate({row.key.removeprefix(self.PREFIX): row.value for row in rows})

    def update(self, **change: Any) -> PhonePageConfig:
        updated = PhonePageConfig.model_validate({**self.load().model_dump(), **change})
        dumped = updated.model_dump(mode="json")
        with self._db.session() as s:
            for key in change:
                s.merge(Setting(key=self.PREFIX + key, value=dumped[key]))
            s.commit()
        return updated
