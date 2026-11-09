from datetime import UTC, date, datetime, time

from tests.helpers import mention
from where_to_go.domain import UpdateKind
from where_to_go.resolution import EventResolver

resolver = EventResolver("не распознано")
EARLY = datetime(2026, 11, 1, tzinfo=UTC)
LATE = datetime(2026, 11, 5, tzinfo=UTC)


def test_organizer_outranks_newer_afisha():
    event = resolver.resolve(
        1, 1, [mention(1, at=time(19, 0), organizer=True, published=EARLY), mention(2, at=time(19, 30), published=LATE)]
    )
    assert event.start_time == time(19, 0)


def test_disagreeing_times_are_kept_as_a_conflict():
    event = resolver.resolve(1, 1, [mention(1, at=time(19, 0)), mention(2, at=time(19, 30), published=LATE)])
    assert [(c.field, c.values) for c in event.conflicts] == [("start_time", ("19:30", "19:00"))]


def test_reschedule_replaces_the_old_date_without_a_conflict():
    event = resolver.resolve(
        1,
        1,
        [mention(1, day=date(2026, 11, 13)), mention(2, day=date(2026, 11, 20), published=LATE, update=UpdateKind.RESCHEDULE)],
    )
    assert event.start_date == date(2026, 11, 20)
    assert event.conflicts == ()


def test_cancellation_is_undone_by_a_later_announcement():
    cancelled = mention(2, published=LATE, update=UpdateKind.CANCELLATION)
    assert resolver.resolve(1, 1, [mention(1), cancelled]).is_cancelled
    revived = mention(3, published=datetime(2026, 11, 7, tzinfo=UTC))
    assert not resolver.resolve(1, 1, [mention(1), cancelled, revived]).is_cancelled


def test_unknown_time_is_filled_by_any_source_that_knows_it():
    event = resolver.resolve(1, 1, [mention(1, at=None, organizer=True), mention(2, at=time(20, 0))])
    assert event.start_time == time(20, 0)


def test_fallback_tag_only_when_no_real_tag():
    event = resolver.resolve(1, 1, [mention(1, tags=("не распознано",)), mention(2, tags=("Концерт",))])
    assert event.tags == ("Концерт",)


def test_card_text_comes_from_the_full_announcement_not_a_later_digest_line():
    from dataclasses import replace

    full = mention(1, published=EARLY)
    full = replace(full, data=replace(full.data, title="Керамика: кружка своими руками", description="Длинное подробное описание занятия с глиной."))
    digest = mention(2, at=time(17, 0), published=LATE)
    digest = replace(digest, data=replace(digest.data, title="Керамика", description="Коротко."))
    event = resolver.resolve(1, 1, [full, digest])
    assert (event.title, event.description) == ("Керамика: кружка своими руками", "Длинное подробное описание занятия с глиной.")
    assert event.start_time == time(17, 0)
