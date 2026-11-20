from datetime import UTC, date, datetime, time

from tests.helpers import mention
from where_to_go.models import Event, EventKind, UpdateKind
from where_to_go.resolution import EventResolver

resolver = EventResolver(lambda: "не распознано")


def resolve(mentions):
    return resolver.resolve(Event(id=1, city_id=1, title="", original_title="", description="", kind="single", start_date=mentions[0].data.start_date), mentions)
EARLY = datetime(2026, 11, 1, tzinfo=UTC)
LATE = datetime(2026, 11, 5, tzinfo=UTC)


def test_organizer_outranks_newer_afisha():
    event = resolve([mention(1, at=time(19, 0), organizer=True, published=EARLY), mention(2, at=time(19, 30), published=LATE)]
    )
    assert event.start_time == time(19, 0)


def test_disagreeing_times_are_kept_as_a_conflict():
    event = resolve([mention(1, at=time(19, 0)), mention(2, at=time(19, 30), published=LATE)])
    assert [(c.field, c.values) for c in event.conflicts] == [("start_time", ["19:30", "19:00"])]


def test_reschedule_replaces_the_old_date_without_a_conflict():
    event = resolve([mention(1, day=date(2026, 11, 13)), mention(2, day=date(2026, 11, 20), published=LATE, update=UpdateKind.RESCHEDULE)],
    )
    assert event.start_date == date(2026, 11, 20)
    assert event.conflicts == []


def test_cancellation_is_undone_by_a_later_announcement():
    cancelled = mention(2, published=LATE, update=UpdateKind.CANCELLATION)
    assert resolve([mention(1), cancelled]).is_cancelled
    revived = mention(3, published=datetime(2026, 11, 7, tzinfo=UTC))
    assert not resolve([mention(1), cancelled, revived]).is_cancelled


def test_unknown_time_is_filled_by_any_source_that_knows_it():
    event = resolve([mention(1, at=None, organizer=True), mention(2, at=time(20, 0))])
    assert event.start_time == time(20, 0)


def test_fallback_tag_only_when_no_real_tag():
    event = resolve([mention(1, tags=("не распознано",)), mention(2, tags=("Концерт",))])
    assert event.tags == ["Концерт"]


def test_card_text_comes_from_the_full_announcement_not_a_later_digest_line():
    full = mention(1, published=EARLY, title="Керамика: кружка своими руками", description="Длинное подробное описание занятия с глиной.")
    digest = mention(2, at=time(17, 0), published=LATE, title="Керамика", description="Коротко.")
    event = resolve([full, digest])
    assert (event.title, event.description) == ("Керамика: кружка своими руками", "Длинное подробное описание занятия с глиной.")
    assert event.start_time == time(17, 0)


def test_price_is_a_number_with_its_currency():
    event = resolve([mention(1, price=1500.0), mention(2, price=None, published=LATE)])
    assert (event.price, event.currency) == (1500.0, "RSD")


def test_free_is_a_price_not_a_missing_one():
    event = resolve([mention(1, price=0.0, organizer=True), mention(2, price=500.0, published=LATE)])
    assert event.price == 0


def test_a_card_is_a_priority_when_any_of_its_posts_says_so():
    flagged = mention(2, published=EARLY)
    flagged.data.is_priority = True
    assert resolve([mention(1, published=LATE), flagged]).is_priority
    assert not resolve([mention(1)]).is_priority


def weekly(mention_id, published=EARLY):
    found = mention(mention_id, day=date(2026, 11, 7), published=published)
    found.data = found.data.model_copy(update={"kind": EventKind.RECURRING, "rrule": "FREQ=WEEKLY;BYDAY=SA"})
    return found


def test_one_date_of_a_recurring_event_keeps_its_schedule():
    event = resolve([weekly(1), mention(2, day=date(2026, 11, 21), at=time(13, 0), published=LATE)])
    assert (event.kind, event.start_date, event.rrule) == (EventKind.RECURRING, date(2026, 11, 7), "FREQ=WEEKLY;BYDAY=SA")
    assert event.conflicts == []


def test_a_date_off_the_schedule_still_wins_as_the_newer_one():
    event = resolve([weekly(1), mention(2, day=date(2026, 11, 20), published=LATE)])
    assert (event.kind, event.start_date) == (EventKind.SINGLE, date(2026, 11, 20))


def with_pictures(m, paths, index):
    m.post.image_paths, m.image_index = paths, index
    return m


def test_the_card_keeps_the_photos_of_its_posts_and_only_its_line_of_a_digest():
    own = with_pictures(mention(1, description="Подробное описание вечера"), ["a.jpg", "b.jpg"], 0)
    digest = with_pictures(mention(2, published=LATE), ["x.jpg", "y.jpg"], 1)
    event = resolver.resolve(resolve([own]).model_copy(), [own, digest], frozenset({2}))
    assert event.image_paths == ["a.jpg", "b.jpg", "y.jpg"]
