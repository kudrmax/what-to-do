from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from where_to_go.domain import Conflict, Event, EventKind, Mark, Mention, UpdateKind

T = TypeVar("T")

MAX_TAGS = 3


class EventResolver:
    """Builds an event card from every post that mentions it.

    The organizer's own channel outranks an afisha, a newer post outranks an older one.
    Disagreements are kept visible as conflicts, except where a reschedule superseded older posts.
    """

    def __init__(self, fallback_tag: str) -> None:
        self._fallback_tag = fallback_tag

    def resolve(self, event_id: int, city_id: int, mentions: list[Mention], mark: Mark = Mark()) -> Event:
        if not mentions:
            raise ValueError("an event needs at least one mention")
        ranked = sorted(mentions, key=lambda m: (m.data.from_organizer, m.published_at), reverse=True)
        schedule = self._schedule_mentions(ranked)
        lead = schedule[0].data
        return Event(
            id=event_id,
            city_id=city_id,
            kind=lead.kind,
            title=self._first(ranked, lambda m: m.data.title) or lead.title,
            original_title=self._first(ranked, lambda m: m.data.original_title) or lead.original_title,
            description=self._first(ranked, lambda m: m.data.description) or "",
            start_date=lead.start_date,
            end_date=lead.end_date if lead.kind is EventKind.MULTIDAY else None,
            start_time=self._first(schedule, lambda m: m.data.start_time if m.data.start_date == lead.start_date else None),
            rrule=lead.rrule if lead.kind is EventKind.RECURRING else None,
            venue=self._first(ranked, lambda m: m.data.venue),
            address=self._first(ranked, lambda m: m.data.address),
            price=self._first(ranked, lambda m: m.data.price),
            tags=self._tags(ranked),
            image_path=self._first(ranked, lambda m: m.image_path),
            is_cancelled=self._is_cancelled(mentions),
            conflicts=self._conflicts(schedule),
            source_ids=tuple(sorted({m.source_id for m in mentions})),
            mark=mark,
        )

    @staticmethod
    def _schedule_mentions(ranked: list[Mention]) -> list[Mention]:
        reschedules = [m for m in ranked if m.data.update_kind is UpdateKind.RESCHEDULE]
        if not reschedules:
            return ranked
        cutoff = max(m.published_at for m in reschedules)
        return [m for m in ranked if m.published_at >= cutoff]

    @staticmethod
    def _is_cancelled(mentions: list[Mention]) -> bool:
        decisive = [m for m in mentions if m.data.update_kind is not UpdateKind.DETAILS]
        latest = max(decisive, key=lambda m: m.published_at, default=None)
        return latest is not None and latest.data.update_kind is UpdateKind.CANCELLATION

    @staticmethod
    def _first(mentions: Iterable[Mention], value: Callable[[Mention], T | None]) -> T | None:
        for mention in mentions:
            found = value(mention)
            if found:
                return found
        return None

    def _tags(self, ranked: list[Mention]) -> tuple[str, ...]:
        tags = list(dict.fromkeys(t for m in ranked for t in m.data.tags if t != self._fallback_tag))
        return tuple(tags[:MAX_TAGS]) or (self._fallback_tag,)

    @staticmethod
    def _conflicts(schedule: list[Mention]) -> tuple[Conflict, ...]:
        fields: dict[str, Callable[[Mention], str | None]] = {
            "start_date": lambda m: m.data.start_date.isoformat(),
            "start_time": lambda m: m.data.start_time.strftime("%H:%M") if m.data.start_time else None,
        }
        conflicts = []
        for name, value in fields.items():
            values = tuple(dict.fromkeys(v for v in map(value, schedule) if v))
            if len(values) > 1:
                conflicts.append(Conflict(name, values))
        return tuple(conflicts)
