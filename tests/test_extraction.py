import json
from datetime import UTC, date, datetime, time

import pytest

from tests.helpers import FakeLlm, raw_event
from where_to_go.domain import City, EventKind, Post, Source, SourceKind, UpdateKind
from where_to_go.extraction import ExtractionContext, PostExtractor

CONTEXT = ExtractionContext(City(1, "Белград", "Europe/Belgrade"), "русский", ["Лекция", "Концерт"], "не распознано")
SOURCES = {1: Source(1, 1, SourceKind.TELEGRAM, "bg", "Афиша")}


def post(post_id: int = 10, images: int = 0) -> Post:
    return Post(post_id, 1, post_id, f"https://t.me/bg/{post_id}", datetime(2026, 11, 9, 17, 30, tzinfo=UTC), "текст",
                tuple(f"{i}.jpg" for i in range(images)))


async def extract_one(events: list[dict], images: int = 0, places: list[dict] | None = None):
    llm = FakeLlm(lambda *_: {"posts": [{"post_id": 10, "events": events, "places": places or []}]})
    [result] = await PostExtractor(llm).extract([post(images=images)], SOURCES, CONTEXT)
    return result, llm


async def test_valid_event_is_converted_with_types():
    result, _ = await extract_one([raw_event("Кафаны", "2026-11-13", "19:00", price="800 RSD", update_kind="reschedule")])
    [event] = result.events
    assert (event.start_date, event.start_time, event.price) == (date(2026, 11, 13), time(19, 0), "800 RSD")
    assert event.update_kind is UpdateKind.RESCHEDULE


@pytest.mark.parametrize("field,value", [("start_date", "13 ноября"), ("start_time", "вечером"), ("rrule", "каждый вторник")])
async def test_item_with_unreadable_values_is_dropped_not_the_whole_post(field, value):
    broken = raw_event("Плохое", "2026-11-13", kind="recurring" if field == "rrule" else "single", **{field: value})
    result, _ = await extract_one([broken, raw_event("Хорошее", "2026-11-14")])
    assert [e.title for e in result.events] == ["Хорошее"]


async def test_multiday_without_a_real_end_becomes_single():
    result, _ = await extract_one([raw_event("Выставка", "2026-11-13", None, kind="multiday", end_date="2026-11-13")])
    assert (result.events[0].kind, result.events[0].end_date) == (EventKind.SINGLE, None)


async def test_recurring_without_rule_becomes_single_and_single_drops_stray_fields():
    result, _ = await extract_one([
        raw_event("Квиз", "2026-11-13", kind="recurring", rrule=None),
        raw_event("Лекция", "2026-11-13", end_date="2026-11-20", rrule="FREQ=WEEKLY"),
    ])
    assert [(e.kind, e.end_date, e.rrule) for e in result.events] == [(EventKind.SINGLE, None, None)] * 2


async def test_tags_outside_the_list_fall_back():
    result, _ = await extract_one([raw_event("А", "2026-11-13", tags=["Танцы"]), raw_event("Б", "2026-11-13", tags=["Танцы", "Концерт", "Концерт"])])
    assert [e.tags for e in result.events] == [("не распознано",), ("Концерт",)]


async def test_image_index_is_checked_against_the_post():
    result, _ = await extract_one([raw_event("А", "2026-11-13", image_index=5)], images=2)
    assert result.events[0].image_index is None


async def test_only_image_goes_to_the_only_event_but_not_to_digest_items():
    single, _ = await extract_one([raw_event("А", "2026-11-13")], images=1)
    digest, _ = await extract_one([raw_event("А", "2026-11-13"), raw_event("Б", "2026-11-14")], images=1)
    assert single.events[0].image_index == 0
    assert [e.image_index for e in digest.events] == [None, None]


async def test_places_are_kept_apart_from_events():
    result, _ = await extract_one([], places=[{"name": "Скалодром", "address": None, "description": "Открыт каждый день"}])
    assert result.events == () and result.places[0].name == "Скалодром"


async def test_post_missing_from_the_answer_yields_nothing():
    llm = FakeLlm(lambda *_: {"posts": []})
    [result] = await PostExtractor(llm).extract([post()], SOURCES, CONTEXT)
    assert result.events == () and result.places == ()


async def test_prompt_gives_local_publication_time_tags_and_language():
    _, llm = await extract_one([])
    system, prompt = llm.calls[0]
    assert '"Лекция", "Концерт"' in system and "русский" in system and "Белград" in system
    item = json.loads(prompt.split("\n", 1)[1])[0]
    assert item["published"] == "2026-11-09 18:30 (Monday)" and item["channel"] == "Афиша"


def test_posts_are_read_in_batches():
    batches = PostExtractor(FakeLlm(lambda *_: {})).batches([post(i) for i in range(20)])
    assert [len(b) for b in batches] == [8, 8, 4]
