from datetime import date, time

from where_to_go.feed import Feed, FeedFilter, PlanFilter
from where_to_go.models import Event, EventKind, Plan


def event(**overrides) -> Event:
    base = dict(
        id=1, city_id=1, kind=EventKind.SINGLE, title="Квиз", original_title="Квиз", description="", start_date=date(2026, 11, 10),
        end_date=None, start_time=time(20, 0), rrule=None, venue=None, address=None, price=None, tags=["Игры и квизы"],
        image_path=None, is_cancelled=False,
    )
    base.update(overrides)
    return Event(**base)


class Events:
    def __init__(self, *events: Event) -> None:
        self._events = events

    def near(self, city_id, start, end):
        return list(self._events)

    def in_city(self, city_id):
        return list(self._events)


WEEK = FeedFilter(start=date(2026, 11, 9), end=date(2026, 11, 22))


def test_recurring_event_repeats_inside_the_window():
    weekly = event(kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 10, 6))
    days = [o.date for o in Feed(Events(weekly)).occurrences(1, WEEK)]
    assert days == [date(2026, 11, 10), date(2026, 11, 17)]


def test_running_exhibition_shows_once_on_the_first_visible_day():
    show = event(kind=EventKind.MULTIDAY, start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
    assert [o.date for o in Feed(Events(show)).occurrences(1, WEEK)] == [date(2026, 11, 9)]


def test_plan_filter_selects_unmarked_or_planned_cards():
    unmarked = event(id=1)
    interest_only = event(id=2, interest=2)
    sure = event(id=3, interest=5, plan=Plan.SURE)
    no = event(id=4, plan=Plan.NO)
    feed = Feed(Events(unmarked, interest_only, sure, no))

    def shown(*plans):
        criteria = FeedFilter(start=WEEK.start, end=WEEK.end, plans=frozenset(plans))
        return {o.event.id for o in feed.occurrences(1, criteria)}

    assert shown(PlanFilter.NONE) == {1, 2}
    assert shown(PlanFilter.MAYBE, PlanFilter.SURE) == {3}
    assert shown() == {1, 2, 3, 4}


def test_without_an_end_the_feed_reaches_the_last_dated_event():
    late = event(id=1, start_date=date(2027, 1, 20))
    weekly = event(id=2, kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 11, 3))
    occurrences = Feed(Events(late, weekly)).occurrences(1, FeedFilter(start=date(2026, 11, 9)))
    assert occurrences[-1].event.id == 1
    assert sum(o.event.id == 2 for o in occurrences) == 11


def test_recurring_alone_still_shows_four_weeks():
    weekly = event(kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 11, 3))
    assert len(Feed(Events(weekly)).occurrences(1, FeedFilter(start=date(2026, 11, 9)))) == 4


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
