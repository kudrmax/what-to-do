from datetime import date, time

from where_to_go.domain import Event, EventKind, Mark, Plan
from where_to_go.feed import Feed, FeedFilter


def event(**overrides) -> Event:
    base = dict(
        id=1, city_id=1, kind=EventKind.SINGLE, title="Квиз", original_title="Квиз", description="", start_date=date(2026, 11, 10),
        end_date=None, start_time=time(20, 0), rrule=None, venue=None, address=None, price=None, tags=("Игры и квизы",),
        image_path=None, is_cancelled=False,
    )
    base.update(overrides)
    return Event(**base)


class Events:
    def __init__(self, *events: Event) -> None:
        self._events = events

    def near(self, city_id, start, end):
        return list(self._events)


WEEK = FeedFilter(start=date(2026, 11, 9), end=date(2026, 11, 22))


def test_recurring_event_repeats_inside_the_window():
    weekly = event(kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 10, 6))
    days = [o.date for o in Feed(Events(weekly)).occurrences(1, WEEK)]
    assert days == [date(2026, 11, 10), date(2026, 11, 17)]


def test_running_exhibition_shows_once_on_the_first_visible_day():
    show = event(kind=EventKind.MULTIDAY, start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
    assert [o.date for o in Feed(Events(show)).occurrences(1, WEEK)] == [date(2026, 11, 9)]


def test_fully_marked_not_going_is_hidden_by_default_but_going_stays():
    no = event(id=1, mark=Mark(3, Plan.NO))
    sure = event(id=2, mark=Mark(5, Plan.SURE))
    unrated = event(id=3, mark=Mark(None, Plan.NO))
    shown = {o.event.id for o in Feed(Events(no, sure, unrated)).occurrences(1, WEEK)}
    assert shown == {2, 3}


def test_only_timed_drops_unknown_time_and_multiday():
    feed = Feed(Events(event(id=1), event(id=2, start_time=None), event(id=3, kind=EventKind.MULTIDAY, end_date=date(2026, 11, 12))))
    criteria = FeedFilter(start=WEEK.start, end=WEEK.end, only_timed=True)
    assert [o.event.id for o in feed.occurrences(1, criteria)] == [1]


def test_day_order_puts_timed_first_then_unknown_time_then_multiday():
    feed = Feed(Events(
        event(id=1, kind=EventKind.MULTIDAY, start_date=date(2026, 11, 9), end_date=date(2026, 11, 12)),
        event(id=2, start_date=date(2026, 11, 9), start_time=None),
        event(id=3, start_date=date(2026, 11, 9), start_time=time(21, 0)),
        event(id=4, start_date=date(2026, 11, 9), start_time=time(18, 0)),
    ))
    assert [o.event.id for o in feed.occurrences(1, WEEK)] == [4, 3, 2, 1]
