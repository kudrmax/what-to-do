import json
import tempfile
from datetime import UTC, date, datetime, time
from pathlib import Path

import pytest

from tests.helpers import FakeLlm, raw_event
from where_to_go.models import City, EventKind, Post, Source, UpdateKind
from where_to_go.settings import AppSettings
from where_to_go.extraction import ExtractionContext, PostExtractor
from where_to_go.images import ImageStore

CONTEXT = ExtractionContext(City(id=1, name="Белград", timezone="Europe/Belgrade"), AppSettings().extraction_prompt, "русский", ["Лекция", "Концерт"], "не распознано")
SOURCES = {1: Source(id=1, city_id=1, handle="bg", title="Афиша")}


def post(post_id: int = 10, images: int = 0) -> Post:
    return Post(id=post_id, source_id=1, external_id=post_id, url=f"https://t.me/bg/{post_id}",
                published_at=datetime(2026, 11, 9, 17, 30, tzinfo=UTC), text="текст", image_paths=[f"{i}.jpg" for i in range(images)])


def photo_store(*names: str) -> ImageStore:
    """A store holding the given stored image names, each a few distinct bytes."""
    folder = Path(tempfile.mkdtemp())
    for name in names:
        (folder / name).write_bytes(name.encode())
    return ImageStore(folder, client=None)


def extractor(llm, store: ImageStore | None = None) -> PostExtractor:
    return PostExtractor(llm, store or photo_store())


def events(result):
    return [event for event, _ in result.events]


async def extract_one(events: list[dict], images: int = 0, places: list[dict] | None = None):
    llm = FakeLlm(lambda *_: {"posts": [{"post_id": 10, "events": events, "places": places or []}]})
    store = photo_store(*(f"{i}.jpg" for i in range(images)))
    [result] = await extractor(llm, store).extract([post(images=images)], SOURCES, CONTEXT)
    return result, llm


async def test_valid_event_is_converted_with_types():
    result, _ = await extract_one([raw_event("Кафаны", "2026-11-13", "19:00", price=800, currency="RSD", update_kind="reschedule")])
    [event] = events(result)
    assert (event.start_date, event.start_time, event.price, event.currency) == (date(2026, 11, 13), time(19, 0), 800, "RSD")
    assert event.update_kind is UpdateKind.RESCHEDULE


@pytest.mark.parametrize("field,value", [("start_date", "13 ноября"), ("start_time", "вечером"), ("price", "800 RSD")])
async def test_item_with_unreadable_values_is_dropped_not_the_whole_post(field, value):
    broken = raw_event("Плохое", "2026-11-13", **{field: value})
    result, _ = await extract_one([broken, raw_event("Хорошее", "2026-11-14")])
    assert [e.title for e in events(result)] == ["Хорошее"]


async def test_unreadable_rule_makes_a_single_event_and_free_has_no_currency():
    result, _ = await extract_one([raw_event("Квиз", "2026-11-13", kind="recurring", rrule="каждый вторник", price=0, currency="RSD")])
    [event] = events(result)
    assert (event.kind, event.rrule, event.price, event.currency) == (EventKind.SINGLE, None, 0, None)


async def test_multiday_without_a_real_end_becomes_single():
    result, _ = await extract_one([raw_event("Выставка", "2026-11-13", None, kind="multiday", end_date="2026-11-13")])
    assert (events(result)[0].kind, events(result)[0].end_date) == (EventKind.SINGLE, None)


async def test_recurring_without_rule_becomes_single_and_single_drops_stray_fields():
    result, _ = await extract_one([
        raw_event("Квиз", "2026-11-13", kind="recurring", rrule=None),
        raw_event("Лекция", "2026-11-13", end_date="2026-11-20", rrule="FREQ=WEEKLY"),
    ])
    assert [(e.kind, e.end_date, e.rrule) for e in events(result)] == [(EventKind.SINGLE, None, None)] * 2


async def test_tags_outside_the_list_fall_back():
    result, _ = await extract_one([raw_event("А", "2026-11-13", tags=["Танцы"]), raw_event("Б", "2026-11-13", tags=["Танцы", "Концерт", "Концерт"])])
    assert [e.tags for e in events(result)] == [["не распознано"], ["Концерт"]]


async def test_claude_sees_the_photos_of_each_post_captioned_with_post_and_index():
    llm = FakeLlm(lambda *_: {"posts": []})
    store = photo_store("a.jpg", "b.png", "c.jpg")
    first = post(10, images=0).model_copy(update={"image_paths": ["a.jpg", "b.png"]})
    second = post(11, images=0).model_copy(update={"image_paths": ["gone.jpg", "c.jpg"]})
    await extractor(llm, store).extract([first, second], SOURCES, CONTEXT)
    sent = [(i.caption, i.media_type, i.data) for i in llm.images[0]]
    assert sent == [
        ("Post 10, photo 0:", "image/jpeg", b"a.jpg"),
        ("Post 10, photo 1:", "image/png", b"b.png"),
        ("Post 11, photo 1:", "image/jpeg", b"c.jpg"),
    ]
    items = json.loads(llm.calls[0][1].split("\n", 1)[1])
    assert [item["photos"] for item in items] == [2, 1]


async def test_each_event_gets_the_photo_claude_points_at_if_claude_saw_it():
    result, _ = await extract_one(
        [raw_event("А", "2026-11-13", photo=1), raw_event("Б", "2026-11-14", photo=None), raw_event("В", "2026-11-15", photo=7)],
        images=2,
    )
    assert [image for _, image in result.events] == [1, None, None]


async def test_at_most_ten_photos_of_a_post_are_sent():
    _, llm = await extract_one([], images=12)
    assert len(llm.images[0]) == 10


async def test_places_are_kept_apart_from_events():
    result, _ = await extract_one([], places=[{"name": "Скалодром", "address": None, "description": "Открыт каждый день"}])
    assert result.events == [] and result.places[0].name == "Скалодром"


async def test_post_missing_from_the_answer_yields_nothing():
    llm = FakeLlm(lambda *_: {"posts": []})
    [result] = await extractor(llm).extract([post()], SOURCES, CONTEXT)
    assert result.events == [] and result.places == []


async def test_prompt_gives_local_publication_time_tags_and_language():
    _, llm = await extract_one([])
    system, prompt = llm.calls[0]
    assert '"Лекция", "Концерт"' in system and "русский" in system and "Белград" in system
    item = json.loads(prompt.split("\n", 1)[1])[0]
    assert item["published"] == "2026-11-09 18:30 (Monday)" and item["channel"] == "Афиша"
    assert item["photos"] == 0


def test_posts_are_read_in_batches():
    batches = extractor(FakeLlm(lambda *_: {})).batches([post(i) for i in range(20)])
    assert [len(b) for b in batches] == [8, 8, 4]


async def test_the_prompt_comes_from_settings():
    custom = ExtractionContext(CONTEXT.city, "Город {city}, язык {language}", "русский", ["Лекция"], "не распознано")
    llm = FakeLlm(lambda *_: {"posts": []})
    await extractor(llm).extract([post()], SOURCES, custom)
    assert llm.calls[0][0] == "Город Белград, язык русский"


async def test_the_schema_claude_gets_carries_the_field_descriptions():
    _, llm = await extract_one([])
    event = llm.schemas[0]["$defs"]["EventReading"]["properties"]
    assert "0 when free" in event["price"]["description"] and "poster" in event["photo"]["description"]
