from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.helpers import add_city, extraction_by_text, judge_same_titles, photos_saying, raw_event
from where_to_go.container import Container
from where_to_go.models import CollectedPost, ExtractedEvent, Mark, Plan, Source
from where_to_go.phone_page.snapshot import SnapshotBuilder

ZONE = ZoneInfo("Europe/Belgrade")
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
TODAY = NOW.astimezone(ZONE).date()


@pytest.fixture
def container(tmp_path):
    return Container.build(tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), photo_llm=photos_saying())


@pytest.fixture
def builder(container):
    return SnapshotBuilder(container.feed, container.cities, container.tags, container.mentions, container.images)


def seed(container, title: str, day: date, plan: Plan | None = None, handle: str = "a") -> int:
    city = container.cities.active() or add_city(container, "Белград", "Europe/Belgrade")
    source = next((s for s in container.sources.in_city(city.id) if s.handle == handle), None) or container.sources.add(
        Source(city_id=city.id, handle=handle, title=handle)
    )
    external = len(container.posts.known_ids(source.id)) + 1
    post = CollectedPost(external_id=external, url=f"https://t.me/{handle}/{external}", published_at=NOW, text="текст")
    container.posts.add_new(source.id, post, [])
    stored = next(p for p in container.posts.unprocessed([source.id]) if p.external_id == external)
    mention = container.mentions.add(stored.id, 0, ExtractedEvent.model_validate(raw_event(title, day.isoformat())), None)
    container.posts.mark_processed(stored.id, "test")
    event_id = container.cards.create(city.id, mention)
    container.cards.refresh(event_id)
    if plan:
        container.events.set_mark(event_id, Mark(plan=plan))
    return event_id


def test_only_upcoming_sure_and_maybe(container, builder):
    seed(container, "Sure", TODAY + timedelta(days=1), Plan.SURE)
    seed(container, "Maybe", TODAY, Plan.MAYBE)
    seed(container, "No", TODAY + timedelta(days=1), Plan.NO)
    seed(container, "Went", TODAY - timedelta(days=1), Plan.WENT)
    seed(container, "Unmarked", TODAY + timedelta(days=1))

    snapshot, _ = builder.build(NOW)

    assert [o.event["title"] for o in snapshot.occurrences] == ["Maybe", "Sure"]
    assert snapshot.city == container.cities.active().label
    assert snapshot.timezone == "Europe/Belgrade" and snapshot.today == TODAY
    assert snapshot.tags == [t.name for t in container.tags.all()]
    assert snapshot.occurrences[0].post_url == "https://t.me/a/2"


def test_image_url_points_to_encrypted_file(container, builder, tmp_path):
    event_id = seed(container, "Show", TODAY, Plan.SURE)
    event = container.events.get(event_id)
    event.image_path = "abc.jpg"
    container.events.save(event)
    (tmp_path / "images" / "abc.jpg").write_bytes(b"jpeg")

    snapshot, files = builder.build(NOW)

    assert snapshot.occurrences[0].event["image_url"] == "images/abc.bin"
    assert files == {"images/abc.bin": container.images.path("abc.jpg")}


def test_missing_poster_is_left_out(container, builder):
    event_id = seed(container, "Show", TODAY, Plan.SURE)
    event = container.events.get(event_id)
    event.image_path = "abc.jpg"
    container.events.save(event)

    snapshot, files = builder.build(NOW)

    assert snapshot.occurrences[0].event["image_url"] is None
    assert files == {}


def test_hash_ignores_made_at(container, builder):
    seed(container, "Show", TODAY, Plan.SURE)
    other = seed(container, "Other", TODAY, None)

    first, _ = builder.build(NOW)
    later, _ = builder.build(NOW + timedelta(minutes=5))
    assert first.made_at != later.made_at and first.content_hash() == later.content_hash()

    container.events.set_mark(other, Mark(plan=Plan.MAYBE))
    changed, _ = builder.build(NOW)
    assert changed.content_hash() != first.content_hash()


def test_no_active_city_gives_none(builder):
    assert builder.build(NOW) is None
