from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from where_to_go.models import Conflict, ConflictField, Event, EventFacts, Mention, UpdateKind

T = TypeVar("T")

MAX_TAGS = 3

TEXT_FIELDS = ("title", "original_title", "description")
SCHEDULE_FIELDS = ("kind", "start_date", "end_date", "rrule")
DETAIL_FIELDS = tuple(f for f in EventFacts.model_fields if f not in (*TEXT_FIELDS, *SCHEDULE_FIELDS, "start_time", "tags"))


class EventResolver:
    """Builds a card from every post that mentions it.

    The organizer's own channel outranks an afisha. For the schedule a newer post outranks an older one,
    and a reschedule supersedes what came before it. The text comes from the fullest announcement, not from
    a one-line digest entry posted later. Disagreements stay visible as conflicts.
    """

    def __init__(self, fallback_tag: Callable[[], str]) -> None:
        self._fallback_tag = fallback_tag

    def resolve(self, card: Event, mentions: list[Mention]) -> Event:
        if not mentions:
            raise ValueError("a card needs at least one mention")
        newest = sorted(mentions, key=lambda m: (m.data.from_organizer, m.published_at), reverse=True)
        fullest = sorted(mentions, key=lambda m: (m.data.from_organizer, len(m.data.description)), reverse=True)
        schedule = self._schedule([m for m in newest if not m.data.is_dateless_follow_up])
        lead = schedule[0].data
        facts = {name: getattr(lead, name) for name in SCHEDULE_FIELDS}
        facts |= {name: self._first(fullest, lambda m, n=name: getattr(m.data, n)) or "" for name in TEXT_FIELDS}
        facts |= {name: self._first(newest, lambda m, n=name: getattr(m.data, n)) for name in DETAIL_FIELDS}
        facts["start_time"] = self._first(schedule, lambda m: m.data.start_time if m.data.start_date == lead.start_date else None)
        facts["tags"] = self._tags(newest)
        card.sqlmodel_update(EventFacts.model_validate(facts).model_dump(include=set(EventFacts.model_fields)))
        card.image_path = self._first(fullest, lambda m: m.image_path)
        card.is_cancelled = self._is_cancelled(mentions)
        card.conflicts = self._conflicts(schedule)
        card.source_ids = sorted({m.source_id for m in mentions})
        return card

    @staticmethod
    def _schedule(newest: list[Mention]) -> list[Mention]:
        reschedules = [m.published_at for m in newest if m.data.update_kind is UpdateKind.RESCHEDULE]
        return [m for m in newest if m.published_at >= max(reschedules)] if reschedules else newest

    @staticmethod
    def _is_cancelled(mentions: list[Mention]) -> bool:
        decisive = [m for m in mentions if m.data.update_kind is not UpdateKind.DETAILS]
        latest = max(decisive, key=lambda m: m.published_at, default=None)
        return latest is not None and latest.data.update_kind is UpdateKind.CANCELLATION

    @staticmethod
    def _first(mentions: Iterable[Mention], value: Callable[[Mention], T | None]) -> T | None:
        """The first value a mention knows; 0 (a free event) is a value, an empty text is not."""
        return next((found for found in map(value, mentions) if found is not None and found != ""), None)

    def _tags(self, newest: list[Mention]) -> list[str]:
        fallback = self._fallback_tag()
        tags = list(dict.fromkeys(t for m in newest for t in m.data.tags if t != fallback))
        return tags[:MAX_TAGS] or [fallback]

    @staticmethod
    def _conflicts(schedule: list[Mention]) -> list[Conflict]:
        readings: dict[ConflictField, Callable[[Mention], str | None]] = {
            ConflictField.START_DATE: lambda m: m.data.start_date.isoformat(),
            ConflictField.START_TIME: lambda m: m.data.start_time.strftime("%H:%M") if m.data.start_time else None,
        }
        conflicts = []
        for field, read in readings.items():
            values = list(dict.fromkeys(v for v in map(read, schedule) if v))
            if len(values) > 1:
                conflicts.append(Conflict(field=field, values=values))
        return conflicts
