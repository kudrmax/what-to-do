"""Claude gives the upcoming cards their tags again, after the user changed the tag list or what the tags mean."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import anyio
from pydantic import computed_field
from sqlmodel import Field, SQLModel

from where_to_go.extraction import TagList
from where_to_go.llm import JsonLlm, LlmError, ReaderNotReadyError
from where_to_go.models import Event, EventKind, Public
from where_to_go.repositories import CityRepository, EventRepository, TagRepository
from where_to_go.resolution import MAX_TAGS

log = logging.getLogger(__name__)

RETAGGING = """You tag event cards for a person who looks for things to do in person.

For every card give every allowed tag that fits it, one to four: what kind of event it is, and also its format or genre when a tag says so. A jazz concert is both a concert and jazz.
A tag's meaning, when given after a dash, decides which events get it, over its name.
Allowed tags:
{tags}
If none fits, use exactly "{fallback}"."""


class CardTags(SQLModel):
    id: int = Field(description="The card's id as given")
    tags: list[str] = Field(description="One to four tags from the allowed list: every tag whose meaning fits the card")


class Retagging(SQLModel):
    cards: list[CardTags] = Field(description="One item per card given")


class EventRetagger:
    """Tags a card the way posts are read now. The card's announcements get the same tags, so a card built
    again from them keeps what Claude gave it here."""

    BATCH_SIZE = 30

    def __init__(self, llm: JsonLlm, cities: CityRepository, events: EventRepository, tags: TagRepository) -> None:
        self._llm = llm
        self._cities = cities
        self._events = events
        self._tags = tags

    def upcoming(self) -> list[Event]:
        """Cards of every city still ahead: the past ones are not in the feed, so their tags do not matter."""
        found: list[Event] = []
        for city in self._cities.all():
            today = datetime.now(ZoneInfo(city.timezone)).date()
            found += [e for e in self._events.in_city(city.id) if e.kind is EventKind.RECURRING or (e.end_date or e.start_date) >= today]
        return found

    def batches(self, events: Sequence[Event]) -> list[list[Event]]:
        return [list(events[i : i + self.BATCH_SIZE]) for i in range(0, len(events), self.BATCH_SIZE)]

    async def retag(self, batch: list[Event]) -> int:
        """Gives the cards of a batch their new tags; returns how many cards changed."""
        tags = self._tags.all()
        names = [t.name for t in tags if not t.is_fallback]
        fallback = self._tags.fallback()
        system = RETAGGING.format(tags=TagList(names, {t.name: t.description for t in tags if t.description}).lines(), fallback=fallback)
        answer = await self._llm.complete_json(system, self._prompt(batch), Retagging.model_json_schema())
        allowed = set(names) | {fallback}
        given = {item.get("id"): item.get("tags") for item in answer.get("cards", []) if isinstance(item, dict)}
        changed = 0
        for event in batch:
            raw = given.get(event.id)
            if not isinstance(raw, list):
                continue
            chosen = list(dict.fromkeys(t for t in raw if t in allowed and t != fallback))[:MAX_TAGS] or [fallback]
            if chosen != event.tags:
                self._events.retag(event.id, chosen)
                changed += 1
        return changed

    @staticmethod
    def _prompt(batch: list[Event]) -> str:
        cards = [{"id": e.id, "title": e.title, "description": e.description, "venue": e.venue} for e in batch]
        return "Cards:\n" + json.dumps(cards, ensure_ascii=False, indent=1)


class RetagProgress(Public):
    started_at: datetime | None = None
    finished_at: datetime | None = None
    upcoming: int = Field(default=0, description="Cards still ahead in every city: what a re-tagging would read")
    cards_to_retag: int = 0
    cards_retagged: int = Field(default=0, description="Cards Claude has read so far, changed or not")
    cards_changed: int = 0
    claude_calls: int = Field(default=0, description="Calls a re-tagging makes: one per batch of cards")
    errors: list[str] = Field(default_factory=list, description="Human-readable, ready to show")
    active: bool = Field(default=False, exclude=True)

    @computed_field
    @property
    def running(self) -> bool:
        return self.active


class RetagService:
    CONCURRENCY = 3

    def __init__(self, retagger: EventRetagger) -> None:
        self._retagger = retagger
        self.progress = RetagProgress()
        self._task: asyncio.Task | None = None
        self._cancel: anyio.CancelScope | None = None

    def status(self) -> RetagProgress:
        """The current or last re-tagging; when none runs, also how many cards a new one would read."""
        if not self.progress.running:
            upcoming = self._retagger.upcoming()
            self.progress.upcoming = len(upcoming)
            self.progress.claude_calls = len(self._retagger.batches(upcoming))
        return self.progress

    def start(self) -> RetagProgress:
        if not self.progress.running:
            events = self._retagger.upcoming()
            batches = self._retagger.batches(events)
            self.progress = RetagProgress(
                started_at=datetime.now(UTC), upcoming=len(events), cards_to_retag=len(events), claude_calls=len(batches), active=True
            )
            self._cancel = anyio.CancelScope()
            self._task = asyncio.create_task(self._run(batches, self._cancel))
        return self.progress

    async def wait(self) -> RetagProgress:
        if self._task is not None:
            await self._task
        return self.progress

    async def stop(self) -> None:
        if self._task is None or self._cancel is None or self._task.done():
            return
        self._cancel.cancel()
        await asyncio.wait({self._task})

    async def _run(self, batches: list[list[Event]], cancel: anyio.CancelScope) -> None:
        limit = asyncio.Semaphore(self.CONCURRENCY)
        reasons_said: set[type[ReaderNotReadyError]] = set()

        async def one(batch: list[Event]) -> None:
            async with limit:
                try:
                    changed = await self._retagger.retag(batch)
                    self.progress.cards_changed += changed
                except ReaderNotReadyError as error:
                    if type(error) not in reasons_said:
                        reasons_said.add(type(error))
                        self.progress.errors.append(str(error))
                except LlmError as error:
                    self.progress.errors.append(f"Couldn't re-tag {len(batch)} cards: {error}")
                self.progress.cards_retagged += len(batch)

        try:
            with cancel:
                await asyncio.gather(*(one(b) for b in batches))
            if cancel.cancelled_caught:
                self.progress.errors.append("Re-tagging stopped: the app was closed")
        except Exception as error:
            log.exception("re-tagging failed")
            self.progress.errors.append(f"Re-tagging stopped: {error}")
        finally:
            self.progress.active = False
            self.progress.finished_at = datetime.now(UTC)
