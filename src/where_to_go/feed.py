from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from dateutil.rrule import rrulestr
from sqlmodel import Field, SQLModel

from where_to_go.models import City, Event, EventKind, EventPublic, Plan, Public
from where_to_go.repositories import EventRepository, SourceRepository
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
    hidden_tags: frozenset[str] = frozenset()
    source_ids: frozenset[int] = frozenset()
    only_timed: bool = False
    hide_multiday: bool = False
    only_priority: bool = False
    plans: frozenset[PlanFilter] = field(default_factory=frozenset)
    collection: int | None = None
    today: date | None = None
    search: SearchQuery = field(default_factory=lambda: SearchQuery(""))

    def accepts(self, event: Event) -> bool:
        if self.search and not self.search.matches(searchable(event)):
            return False
        if self.tags and not self.tags & set(event.tags):
            return False
        if self.collection is not None and self.collection not in event.collection_ids:
            return False
        if event.plan is None and self.collection is None and self._blocked(event):
            return False
        if self.source_ids and not self.source_ids & set(event.source_ids):
            return False
        if self.only_timed and (event.start_time is None or event.kind is EventKind.MULTIDAY):
            return False
        if self.hide_multiday and event.kind is EventKind.MULTIDAY:
            return False
        if self.only_priority and not event.is_priority:
            return False
        return not self.plans or PlanFilter(event.plan or PlanFilter.NONE) in self.plans


    def _blocked(self, event: Event) -> bool:
        """A card is blocked only when every tag it has is hidden and it fits what the user looks for first."""
        return not event.is_priority and bool(event.tags) and set(event.tags) <= self.hidden_tags


def searchable(event: Event) -> list[str | None]:
    return [event.title, event.original_title, event.description, event.venue, event.address, *event.tags]


class Feed:
    """Events of a city laid out on days: recurring ones repeat, multi-day ones show once.

    Without an end the feed reaches the last dated event the city has; recurring events repeat up to there
    (and at least four weeks ahead, so a city of regular events alone is not empty).
    Unmarked cards only paused sources announce are left out.
    """

    def __init__(self, events: EventRepository, sources: SourceRepository) -> None:
        self._events = events
        self._sources = sources

    def occurrences(self, city: City, criteria: FeedFilter) -> list[Occurrence]:
        found = self._lay_out(city, criteria)
        if found or not criteria.search:
            return found
        return self._lay_out(city, replace(criteria, search=criteria.search.in_other_layout()))

    def earliest(self, city_id: int) -> date | None:
        return min((e.start_date for e in self._events.in_city(city_id)), default=None)

    def _lay_out(self, city: City, criteria: FeedFilter) -> list[Occurrence]:
        end = criteria.end or self._reach(city.id, criteria.start)
        paused = self._sources.paused_ids(city.id)
        result = []
        for event in self._events.near(city.id, criteria.start, end):
            if not event.is_dropped_with(paused) and criteria.accepts(event):
                public = EventPublic.of(event, city)
                days = self._days(event, criteria.start, end)
                if criteria.collection is not None:
                    days = self._kept_day(days, criteria.today)
                result.extend(Occurrence(date=day, event=public) for day in days)
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
    def _kept_day(days: list[date], today: date | None) -> list[date]:
        """A collection keeps an event once: a regular one on its next date, or on its last one when all have passed."""
        if len(days) < 2:
            return days
        ahead = [d for d in days if today is not None and d >= today]
        return [ahead[0] if ahead else days[-1]]

    @staticmethod
    def _order(occurrence: Occurrence) -> tuple:
        event = occurrence.event
        multiday = event.kind is EventKind.MULTIDAY
        return (occurrence.date, multiday, event.start_time is None, event.start_time or time(), event.title)
