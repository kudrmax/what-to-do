"""Whether a town a website names is the user's city: asked of Claude once per name, then remembered."""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel
from sqlmodel import select

from where_to_go.db import Database
from where_to_go.llm import JsonLlm, LlmError
from where_to_go.models import City, Locality

log = logging.getLogger(__name__)

PROMPT = """You decide whether place names taken from event listings are the city {city} or a part of it (a district, a neighbourhood or a suburb that belongs to the city). The names may be in any language, script or spelling. A different town, even a near one, is not the city."""


class LocalityVerdict(BaseModel):
    name: str
    in_city: bool


class LocalityVerdicts(BaseModel):
    places: list[LocalityVerdict]


class LocalityRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def known(self, city_id: int, names: set[str]) -> dict[str, bool]:
        with self._db.session() as s:
            rows = s.exec(select(Locality).where(Locality.city_id == city_id))
            return {row.name: row.in_city for row in rows if row.name in names}

    def remember(self, city_id: int, verdicts: dict[str, bool]) -> None:
        with self._db.session() as s:
            for name, in_city in verdicts.items():
                s.add(Locality(city_id=city_id, name=name, in_city=in_city))
            s.commit()


class LocalityJudge:
    def __init__(self, llm: JsonLlm, localities: LocalityRepository) -> None:
        self._llm = llm
        self._localities = localities

    async def in_city(self, city: City, names: set[str]) -> dict[str, bool]:
        """A name Claude could not judge counts as the city: the event is read rather than lost."""
        verdicts = self._localities.known(city.id, names)
        unknown = sorted(names - verdicts.keys())
        if unknown:
            learned = await self._ask(city, unknown)
            self._localities.remember(city.id, learned)
            verdicts |= learned
        return {name: verdicts.get(name, True) for name in names}

    async def _ask(self, city: City, names: list[str]) -> dict[str, bool]:
        try:
            answer = await self._llm.complete_json(
                PROMPT.format(city=city.name), json.dumps({"names": names}, ensure_ascii=False), LocalityVerdicts.model_json_schema()
            )
            places = LocalityVerdicts.model_validate(answer).places
        except (LlmError, ValueError) as error:
            log.warning("could not tell which towns are %s: %s", city.name, error)
            return {}
        return {p.name: p.in_city for p in places if p.name in names}
