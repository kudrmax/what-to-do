from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from dateutil.rrule import rrulestr

from where_to_go.domain import Event, EventKind, Plan
from where_to_go.repositories import EventRepository


@dataclass(frozen=True)
class Occurrence:
    event: Event
    date: date


@dataclass(frozen=True)
class FeedFilter:
    start: date
    end: date
    tags: frozenset[str] = frozenset()
    source_ids: frozenset[int] = frozenset()
    only_timed: bool = False
    hide_multiday: bool = False
    hide_marked: bool = True
    plans: frozenset[Plan] = field(default_factory=frozenset)

    def accepts(self, event: Event) -> bool:
        if self.tags and not self.tags & set(event.tags):
            return False
        if self.source_ids and not self.source_ids & set(event.source_ids):
            return False
        if self.only_timed and (event.start_time is None or event.kind is EventKind.MULTIDAY):
            return False
        if self.hide_multiday and event.kind is EventKind.MULTIDAY:
            return False
        if self.plans and event.mark.plan not in self.plans:
            return False
        if self.hide_marked and event.mark.is_dismissed:
            return False
        return True


class Feed:
    """Events of a city laid out on days: recurring ones repeat, multi-day ones show once."""

    def __init__(self, events: EventRepository) -> None:
        self._events = events

    def occurrences(self, city_id: int, criteria: FeedFilter) -> list[Occurrence]:
        result = []
        for event in self._events.near(city_id, criteria.start, criteria.end):
            if criteria.accepts(event):
                result.extend(Occurrence(event, day) for day in self._days(event, criteria.start, criteria.end))
        return sorted(result, key=self._order)

    @staticmethod
    def _days(event: Event, start: date, end: date) -> list[date]:
        if event.kind is EventKind.RECURRING and event.rrule:
            rule = rrulestr(event.rrule, dtstart=datetime.combine(event.start_date, time()))
            first = datetime.combine(max(start, event.start_date), time())
            return [d.date() for d in rule.between(first, datetime.combine(end, time()), inc=True)]
        if event.kind is EventKind.MULTIDAY:
            last = event.end_date or event.start_date
            return [max(start, event.start_date)] if event.start_date <= end and last >= start else []
        return [event.start_date] if start <= event.start_date <= end else []

    @staticmethod
    def _order(occurrence: Occurrence) -> tuple:
        event = occurrence.event
        multiday = event.kind is EventKind.MULTIDAY
        return (occurrence.date, multiday, event.start_time is None, event.start_time or time(), event.title)


DEFAULT_HORIZON = timedelta(days=14)
