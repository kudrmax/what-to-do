from dataclasses import replace
from datetime import date, time

from where_to_go.feed import Feed, FeedFilter, PlanFilter
from where_to_go.models import City, Event, EventKind, Plan
from where_to_go.search import SearchQuery

CITY = City(id=1, name="Белград", country="Сербия", timezone="Europe/Belgrade")


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


class Sources:
    def __init__(self, *paused: int) -> None:
        self._paused = set(paused)

    def paused_ids(self, city_id):
        return self._paused


WEEK = FeedFilter(start=date(2026, 11, 9), end=date(2026, 11, 22))


def test_recurring_event_repeats_inside_the_window():
    weekly = event(kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 10, 6))
    days = [o.date for o in Feed(Events(weekly), Sources()).occurrences(CITY, WEEK)]
    assert days == [date(2026, 11, 10), date(2026, 11, 17)]


def test_running_exhibition_shows_once_on_the_first_visible_day():
    show = event(kind=EventKind.MULTIDAY, start_date=date(2026, 11, 1), end_date=date(2026, 11, 30))
    assert [o.date for o in Feed(Events(show), Sources()).occurrences(CITY, WEEK)] == [date(2026, 11, 9)]


def test_plan_filter_selects_unmarked_or_planned_cards():
    unmarked = event(id=1)
    interest_only = event(id=2, interest=2)
    sure = event(id=3, interest=5, plan=Plan.SURE)
    no = event(id=4, plan=Plan.NO)
    feed = Feed(Events(unmarked, interest_only, sure, no), Sources())

    def shown(*plans):
        criteria = FeedFilter(start=WEEK.start, end=WEEK.end, plans=frozenset(plans))
        return {o.event.id for o in feed.occurrences(CITY, criteria)}

    assert shown(PlanFilter.NONE) == {1, 2}
    assert shown(PlanFilter.MAYBE, PlanFilter.SURE) == {3}
    assert shown() == {1, 2, 3, 4}


def test_without_an_end_the_feed_reaches_the_last_dated_event():
    late = event(id=1, start_date=date(2027, 1, 20))
    weekly = event(id=2, kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 11, 3))
    occurrences = Feed(Events(late, weekly), Sources()).occurrences(CITY, FeedFilter(start=date(2026, 11, 9)))
    assert occurrences[-1].event.id == 1
    assert sum(o.event.id == 2 for o in occurrences) == 11


def test_recurring_alone_still_shows_four_weeks():
    weekly = event(kind=EventKind.RECURRING, rrule="FREQ=WEEKLY;BYDAY=TU", start_date=date(2026, 11, 3))
    assert len(Feed(Events(weekly), Sources()).occurrences(CITY, FeedFilter(start=date(2026, 11, 9)))) == 4


def test_only_timed_drops_unknown_time_and_multiday():
    feed = Feed(Events(event(id=1), event(id=2, start_time=None), event(id=3, kind=EventKind.MULTIDAY, end_date=date(2026, 11, 12))), Sources())
    criteria = FeedFilter(start=WEEK.start, end=WEEK.end, only_timed=True)
    assert [o.event.id for o in feed.occurrences(CITY, criteria)] == [1]


def test_day_order_puts_timed_first_then_unknown_time_then_multiday():
    feed = Feed(Events(
        event(id=1, kind=EventKind.MULTIDAY, start_date=date(2026, 11, 9), end_date=date(2026, 11, 12)),
        event(id=2, start_date=date(2026, 11, 9), start_time=None),
        event(id=3, start_date=date(2026, 11, 9), start_time=time(21, 0)),
        event(id=4, start_date=date(2026, 11, 9), start_time=time(18, 0)),
    ), Sources())
    assert [o.event.id for o in feed.occurrences(CITY, WEEK)] == [4, 3, 2, 1]


def test_search_looks_through_title_description_venue_address_and_tags():
    feed = Feed(
        Events(
            event(id=1, title="Импровизационные игры"),
            event(id=2, title="Концерт", description="Вечер импровизации на рояле"),
            event(id=3, title="Лекция", venue="Дом молодёжи", tags=["Лекции"]),
            event(id=4, title="Ярмарка", original_title="Sajam", address="Кнез Михаилова, 5", tags=[]),
        ), Sources()
    )

    def found(text):
        return {o.event.id for o in feed.occurrences(CITY, replace(WEEK, search=SearchQuery(text)))}

    assert found("импро") == {1, 2}
    assert found("молодеж") == {3}
    assert found("михайл") == {4}
    assert found("квиз") == {1, 2, 3}
    assert found("") == {1, 2, 3, 4}


def test_search_typed_in_the_wrong_layout_is_tried_in_the_other_one():
    feed = Feed(Events(event(id=1, title="Импровизационные игры"), event(id=2, title="Jazz jam")), Sources())

    def found(text):
        return {o.event.id for o in feed.occurrences(CITY, replace(WEEK, search=SearchQuery(text)))}

    assert found("bvghj") == {1}
    assert found("офяя") == {2}


def test_only_priority_keeps_the_flagged_cards():
    feed = Feed(Events(event(id=1, is_priority=True), event(id=2)), Sources())
    criteria = FeedFilter(start=WEEK.start, end=WEEK.end, only_priority=True)
    assert [o.event.id for o in feed.occurrences(CITY, criteria)] == [1]


def test_unmarked_card_only_paused_sources_announce_is_left_out():
    feed = Feed(
        Events(event(id=1, source_ids=[7]), event(id=2, source_ids=[7], interest=4), event(id=3, source_ids=[7, 8]), event(id=4, source_ids=[8])),
        Sources(7),
    )
    assert [o.event.id for o in feed.occurrences(CITY, WEEK)] == [2, 3, 4]


def test_collected_event_stays_when_only_paused_sources_announce_it():
    collected = event(id=1, source_ids=[7], collection_ids=[3])
    forgotten = event(id=2, source_ids=[7])
    feed = Feed(Events(collected, forgotten), Sources(7))
    assert [o.event.id for o in feed.occurrences(CITY, WEEK)] == [1]
    assert [o.event.id for o in feed.occurrences(CITY, replace(WEEK, collection=4))] == []
