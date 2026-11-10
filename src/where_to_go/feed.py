from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from dateutil.rrule import rrulestr
from sqlmodel import Field, SQLModel

from where_to_go.models import Event, EventKind, EventPublic, Plan, Public
from where_to_go.repositories import EventRepository
from where_to_go.search import SearchQuery

PlanFilter = StrEnum("PlanFilter", {"NONE": "none", **{plan.name: plan.value for plan in Plan}})
PlanFilter.__doc__ = "A plan to show, or none for cards the user has not marked yet."

RECURRING_MIN_REACH = timedelta(weeks=4)


class Occurrence(Public):
    date: dt.date = Field(
        description="The day the card is shown on: a recurring event appears once per day, a multiday one once, "
        "on the first day inside the range"
    )
    event: EventPublic


@dataclass(frozen=True)
class FeedFilter:
    start: date
    end: date | None = None
    tags: frozenset[str] = frozenset()
    source_ids: frozenset[int] = frozenset()
    only_timed: bool = False
    hide_multiday: bool = False
    plans: frozenset[PlanFilter] = field(default_factory=frozenset)
    search: SearchQuery = field(default_factory=lambda: SearchQuery(""))

    def accepts(self, event: Event) -> bool:
        if self.search and not self.search.matches(searchable(event)):
            return False
        if self.tags and not self.tags & set(event.tags):
            return False
        if self.source_ids and not self.source_ids & set(event.source_ids):
            return False
        if self.only_timed and (event.start_time is None or event.kind is EventKind.MULTIDAY):
            return False
        if self.hide_multiday and event.kind is EventKind.MULTIDAY:
            return False
        return not self.plans or PlanFilter(event.plan or PlanFilter.NONE) in self.plans


def searchable(event: Event) -> list[str | None]:
    return [event.title, event.original_title, event.description, event.venue, event.address, *event.tags]


class Feed:
    """Events of a city laid out on days: recurring ones repeat, multi-day ones show once.

    Without an end the feed reaches the last dated event the city has; recurring events repeat up to there
    (and at least four weeks ahead, so a city of regular events alone is not empty).
    """

    def __init__(self, events: EventRepository) -> None:
        self._events = events

    def occurrences(self, city_id: int, criteria: FeedFilter) -> list[Occurrence]:
        found = self._lay_out(city_id, criteria)
        if found or not criteria.search:
            return found
        return self._lay_out(city_id, replace(criteria, search=criteria.search.in_other_layout()))

    def earliest(self, city_id: int) -> date | None:
        return min((e.start_date for e in self._events.in_city(city_id)), default=None)

    def _lay_out(self, city_id: int, criteria: FeedFilter) -> list[Occurrence]:
        end = criteria.end or self._reach(city_id, criteria.start)
        result = []
        for event in self._events.near(city_id, criteria.start, end):
            if criteria.accepts(event):
                public = EventPublic.model_validate(event)
                result.extend(Occurrence(date=day, event=public) for day in self._days(event, criteria.start, end))
        return sorted(result, key=self._order)

    def _reach(self, city_id: int, start: date) -> date:
        dated = [e.end_date or e.start_date for e in self._events.in_city(city_id) if e.kind is not EventKind.RECURRING]
        return max([start + RECURRING_MIN_REACH, *dated])

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
