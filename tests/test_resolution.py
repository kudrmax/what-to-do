from datetime import UTC, date, datetime, time

from tests.helpers import mention
from where_to_go.models import Event, UpdateKind
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
