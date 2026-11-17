from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tests.helpers import add_city, extraction_by_text, judge_same_titles, photos_saying, raw_event
from where_to_go.api import create_app
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
    return SnapshotBuilder(
        settings=container.settings,
        cities=container.cities,
        sources=container.sources,
        tags=container.tags,
        feed=container.feed,
        mentions=container.mentions,
        originals=container.originals,
        images=container.images,
    )


def seed(container, title: str, day: date, plan: Plan | None = None, handle: str = "a", photos: list[str] | None = None, poster: int | None = None) -> int:
    city = container.cities.active() or add_city(container, "Белград", "Europe/Belgrade")
    source = next((s for s in container.sources.in_city(city.id) if s.handle == handle), None) or container.sources.add(
        Source(city_id=city.id, handle=handle, title=handle)
    )
    external = len(container.posts.known_ids(source.id)) + 1
    post = CollectedPost(external_id=external, url=f"https://t.me/{handle}/{external}", published_at=NOW, text="текст")
    container.posts.add_new(source.id, post, photos or [])
    stored = next(p for p in container.posts.unprocessed([source.id]) if p.external_id == external)
    mention = container.mentions.add(stored.id, 0, ExtractedEvent.model_validate(raw_event(title, day.isoformat())), poster)
    container.posts.mark_processed(stored.id, "test")
    event_id = container.cards.create(city.id, mention)
    container.cards.refresh(event_id)
    if plan:
        container.events.set_mark(event_id, Mark(plan=plan))
    return event_id


def store_image(tmp_path, name: str) -> None:
    (tmp_path / "images" / name).write_bytes(b"jpeg " + name.encode())


def test_holds_what_the_api_answers(container, builder):
    sure = seed(container, "Sure", TODAY + timedelta(days=1), Plan.SURE)
    seed(container, "Maybe", TODAY, Plan.MAYBE, handle="b")
    seed(container, "No", TODAY + timedelta(days=1), Plan.NO)
    seed(container, "Went", TODAY - timedelta(days=1), Plan.WENT)
    seed(container, "Unmarked", TODAY + timedelta(days=1))

    snapshot, _ = builder.build(NOW)

    with TestClient(create_app(lambda: container)) as api:
        assert snapshot.settings == api.get("/settings").json()
        assert snapshot.cities == api.get("/cities").json()
        assert snapshot.sources == api.get("/sources").json()
        assert snapshot.tags == api.get("/tags").json()
        assert snapshot.occurrences == api.get("/events", params={"start": TODAY.isoformat(), "plans": ["maybe", "sure"]}).json()
        assert snapshot.mentions[str(sure)] == api.get(f"/events/{sure}/mentions").json()
    assert [o["event"]["title"] for o in snapshot.occurrences] == ["Maybe", "Sure"]
    assert set(snapshot.mentions) == {str(o["event"]["id"]) for o in snapshot.occurrences}
    assert snapshot.timezone == "Europe/Belgrade" and snapshot.made_at == NOW


def test_only_the_active_city(container, builder):
    seed(container, "Show", TODAY, Plan.SURE)
    add_city(container, "Нови Сад", "Europe/Belgrade")

    snapshot, _ = builder.build(NOW)

    assert [city["id"] for city in snapshot.cities] == [snapshot.settings["active_city_id"]]


def test_every_image_the_answers_name_is_mapped_to_its_encrypted_file(container, builder, tmp_path):
    seed(container, "Show", TODAY, Plan.SURE, photos=["poster.jpg", "hall.png"], poster=0)
    store_image(tmp_path, "poster.jpg")
    store_image(tmp_path, "hall.png")

    snapshot, files = builder.build(NOW)

    assert snapshot.occurrences[0]["event"]["image_url"] == "/images/poster.jpg"
    assert snapshot.images == {"/images/poster.jpg": "images/poster.bin", "/images/hall.png": "images/hall.bin"}
    assert files == {"images/poster.bin": container.images.path("poster.jpg"), "images/hall.bin": container.images.path("hall.png")}


def test_missing_image_files_are_left_out(container, builder, tmp_path):
    seed(container, "Show", TODAY, Plan.SURE, photos=["poster.jpg", "gone.jpg"], poster=0)
    store_image(tmp_path, "poster.jpg")

    snapshot, files = builder.build(NOW)

    assert snapshot.images == {"/images/poster.jpg": "images/poster.bin"}
    assert list(files) == ["images/poster.bin"]


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
