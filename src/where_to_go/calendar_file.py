from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event as CalendarEvent, vRecur

from where_to_go.about import APP_NAME, VERSION
from where_to_go.models import City, Event, EventKind

ASSUMED_DURATION = timedelta(hours=2)
"""Posts give a start time only; a calendar entry needs an end."""


class EventCalendarFile:
    """One card as an .ics file that Apple Calendar, Google Calendar and Outlook import."""

    MEDIA_TYPE = "text/calendar"

    def __init__(self, event: Event, city: City, post_url: str | None) -> None:
        self._event = event
        self._zone = ZoneInfo(city.timezone)
        self._post_url = post_url

    @property
    def filename(self) -> str:
        return f"event-{self._event.id}.ics"

    def render(self) -> bytes:
        calendar = Calendar()
        calendar.add("prodid", f"-//{APP_NAME}//{VERSION}//RU")
        calendar.add("version", "2.0")
        calendar.add_component(self._entry())
        calendar.add_missing_timezones()
        return calendar.to_ical()

    def _entry(self) -> CalendarEvent:
        event = self._event
        entry = CalendarEvent()
        entry.add("uid", f"event-{event.id}@where-to-go")
        entry.add("dtstamp", datetime.now(ZoneInfo("UTC")))
        entry.add("summary", event.title)
        start, end = self._span()
        entry.add("dtstart", start)
        entry.add("dtend", end)
        if event.kind is EventKind.RECURRING and event.rrule:
            entry.add("rrule", vRecur.from_ical(event.rrule))
        place = ", ".join(dict.fromkeys(p for p in (event.venue, event.address) if p))
        if place:
            entry.add("location", place)
        entry.add("description", "\n\n".join(p for p in (event.description, self._post_url) if p))
        if self._post_url:
            entry.add("url", self._post_url)
        return entry

    def _span(self) -> tuple[date | datetime, date | datetime]:
        """Timed events last ASSUMED_DURATION; multiday and untimed ones are all-day, the end day exclusive."""
        event = self._event
        if event.kind is EventKind.MULTIDAY:
            return event.start_date, (event.end_date or event.start_date) + timedelta(days=1)
        if event.start_time is None:
            return event.start_date, event.start_date + timedelta(days=1)
        start = datetime.combine(event.start_date, event.start_time, self._zone)
        return start, start + ASSUMED_DURATION
