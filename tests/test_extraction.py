import json
from dataclasses import replace
from datetime import UTC, date, datetime, time

import pytest

from tests.helpers import FakeLlm, raw_event
from where_to_go.models import City, EventKind, PhotoText, Post, Source, UpdateKind
from where_to_go.settings import AppSettings
from where_to_go.extraction import ExtractionContext, PostExtractor

BELGRADE = City(id=1, name="Белград", country="Сербия", timezone="Europe/Belgrade", card_language="русский")
CONTEXT = ExtractionContext(BELGRADE, AppSettings().extraction_prompt, ["Лекция", "Концерт"], "не распознано")
SOURCES = {1: Source(id=1, city_id=1, handle="bg", title="Афиша")}


def post(post_id: int = 10, images: int = 0) -> Post:
    return Post(id=post_id, source_id=1, external_id=post_id, url=f"https://t.me/bg/{post_id}",
                published_at=datetime(2026, 11, 9, 17, 30, tzinfo=UTC), text="текст", image_paths=[f"{i}.jpg" for i in range(images)])


def transcribed(*names: str) -> dict[str, PhotoText]:
    return {name: PhotoText(image=name, text=f"текст {name}", shows=f"афиша {name}", read_with="r") for name in names}


def extractor(llm) -> PostExtractor:
    return PostExtractor(llm)


def events(result):
    return [event for event, _ in result.events]


async def extract_one(events: list[dict], images: int = 0, places: list[dict] | None = None):
    llm = FakeLlm(lambda *_: {"posts": [{"post_id": 10, "events": events, "places": places or []}]})
    texts = transcribed(*(f"{i}.jpg" for i in range(images)))
    [result] = await extractor(llm).extract([post(images=images)], SOURCES, CONTEXT, texts)
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


async def test_claude_reads_the_text_of_each_post_photo_by_index_and_never_the_picture():
    llm = FakeLlm(lambda *_: {"posts": []})
    first = post(10).model_copy(update={"image_paths": ["a.jpg", "b.png"]})
    second = post(11).model_copy(update={"image_paths": ["gone.jpg", "c.jpg"]})
    await extractor(llm).extract([first, second], SOURCES, CONTEXT, transcribed("a.jpg", "b.png", "c.jpg"))
    assert llm.images == [[]]
    items = json.loads(llm.calls[0][1].split("\n", 1)[1])
    assert [item["photos"] for item in items] == [
        [{"index": 0, "shows": "афиша a.jpg", "text": "текст a.jpg"}, {"index": 1, "shows": "афиша b.png", "text": "текст b.png"}],
        [{"index": 1, "shows": "афиша c.jpg", "text": "текст c.jpg"}],
    ]


async def test_each_event_gets_the_photo_claude_points_at_if_claude_saw_it():
    result, _ = await extract_one(
        [raw_event("А", "2026-11-13", photo=1), raw_event("Б", "2026-11-14", photo=None), raw_event("В", "2026-11-15", photo=7)],
        images=2,
    )
    assert [image for _, image in result.events] == [1, None, None]



async def test_at_most_ten_photos_of_a_post_are_read():
    _, llm = await extract_one([], images=12)
    assert len(json.loads(llm.calls[0][1].split("\n", 1)[1])[0]["photos"]) == 10


async def test_places_are_kept_apart_from_events():
    result, _ = await extract_one([], places=[{"name": "Скалодром", "address": None, "description": "Открыт каждый день"}])
    assert result.events == [] and result.places[0].name == "Скалодром"


async def test_post_missing_from_the_answer_yields_nothing():
    llm = FakeLlm(lambda *_: {"posts": []})
    [result] = await extractor(llm).extract([post()], SOURCES, CONTEXT, {})
    assert result.events == [] and result.places == []


async def test_prompt_gives_local_publication_time_tags_and_language():
    _, llm = await extract_one([])
    system, prompt = llm.calls[0]
    assert '"Лекция", "Концерт"' in system and "русский" in system and "Белград" in system
    item = json.loads(prompt.split("\n", 1)[1])[0]
    assert item["published"] == "2026-11-09 18:30 (Monday)" and item["channel"] == "Афиша"
    assert item["photos"] == []


def sized(post_id: int, length: int, images: int = 0) -> Post:
    item = post(post_id, images)
    item.text = "x" * length
    return item


def batch_ids(posts: list[Post], texts: dict[str, PhotoText] | None = None) -> list[list[int]]:
    return [[p.id for p in batch] for batch in extractor(FakeLlm(lambda *_: {})).batches(posts, texts or {})]


def test_short_posts_are_read_eight_at_a_time():
    assert [len(b) for b in batch_ids([post(i) for i in range(20)])] == [8, 8, 4]


def test_a_batch_holds_no_more_text_than_claude_reads_in_full():
    """Two digests in one call made Claude skip a third to all of a digest's events; alone it reads every one."""
    limit = PostExtractor.BATCH_CHARS
    posts = [sized(1, 1500), sized(2, 1500), sized(3, limit - 1000), sized(4, 900), sized(5, limit - 500)]
    assert batch_ids(posts) == [[1, 2], [3, 4], [5]]


def test_a_post_longer_than_a_batch_is_read_alone():
    posts = [sized(1, 100), sized(2, PostExtractor.BATCH_CHARS * 2), sized(3, 100)]
    assert batch_ids(posts) == [[1], [2], [3]]


def test_text_on_a_post_photos_counts_toward_its_size():
    """A digest is often a collage of posters with a one-line caption."""
    collage = {"0.jpg": PhotoText(image="0.jpg", text="x" * PostExtractor.BATCH_CHARS, shows="collage", read_with="r")}
    assert batch_ids([sized(1, 100), sized(2, 10, images=1), sized(3, 100)], collage) == [[1], [2], [3]]


async def test_the_prompt_comes_from_settings():
    custom = ExtractionContext(CONTEXT.city, "Город {city}, язык {language}", ["Лекция"], "не распознано")
    llm = FakeLlm(lambda *_: {"posts": []})
    await extractor(llm).extract([post()], SOURCES, custom, {})
    assert llm.calls[0][0].startswith("Город Белград, Сербия, язык русский\n\nPriority")


async def test_the_schema_claude_gets_carries_the_field_descriptions():
    _, llm = await extract_one([])
    event = llm.schemas[0]["$defs"]["EventReading"]["properties"]
    assert "0 when free" in event["price"]["description"] and "poster" in event["photo"]["description"]


def test_an_edited_prompt_reads_no_post_again():
    edited = ExtractionContext(CONTEXT.city, CONTEXT.prompt + "\nRead slowly.", CONTEXT.tags, CONTEXT.fallback_tag)
    assert edited.rules == CONTEXT.rules


def test_a_new_card_language_reads_the_recent_posts_again():
    def speaking(language: str) -> ExtractionContext:
        return replace(CONTEXT, city=CONTEXT.city.model_copy(update={"card_language": language}))

    assert speaking("English").rules != CONTEXT.rules
    assert speaking(" Русский ").rules == CONTEXT.rules
    assert "The description language is English." in speaking("English").system()


def test_claude_is_told_the_city_with_its_country():
    london = replace(CONTEXT, city=City(id=2, name="London", country="United Kingdom", timezone="Europe/London", card_language="English"))
    assert "lives in London, United Kingdom" in london.system()


async def test_claude_is_asked_for_the_booking_link_and_this_events_lines():
    _, llm = await extract_one([])
    event = llm.schemas[0]["$defs"]["EventReading"]["properties"]
    assert "ticket shop" in event["booking"]["description"] and "copied exactly" in event["post_lines"]["description"]


async def test_a_booking_link_and_lines_come_through():
    booking = {"url": "https://tickets.rs/x", "kind": "tickets"}
    result, _ = await extract_one([raw_event("Концерт", "2026-11-13", booking=booking, post_lines=["19:00 Концерт"])])
    [event] = events(result)
    assert (event.booking.url, event.booking.kind, event.post_lines) == ("https://tickets.rs/x", "tickets", ["19:00 Концерт"])


async def test_the_priority_wish_reaches_claude_and_its_flag_comes_back():
    wishful = ExtractionContext(CONTEXT.city, CONTEXT.prompt, CONTEXT.tags, CONTEXT.fallback_tag, "Ищу друзей")
    llm = FakeLlm(lambda *_: {"posts": [{"post_id": 10, "events": [raw_event("Нетворкинг", "2026-11-13", is_priority=True), raw_event("Лекция", "2026-11-14")]}]})
    [result] = await extractor(llm).extract([post()], SOURCES, wishful, {})
    assert "<wish>\nИщу друзей\n</wish>" in llm.calls[0][0]
    assert [e.is_priority for e in events(result)] == [True, False]


async def test_without_a_wish_claude_is_told_to_flag_nothing():
    _, llm = await extract_one([])
    assert "is_priority is always false" in llm.calls[0][0] and "<wish>" not in llm.calls[0][0]


def test_a_new_wish_reads_the_recent_posts_again_and_no_wish_keeps_the_old_readings():
    def wishing(wish: str) -> ExtractionContext:
        return ExtractionContext(CONTEXT.city, CONTEXT.prompt, CONTEXT.tags, CONTEXT.fallback_tag, wish)

    assert wishing("").rules == CONTEXT.rules
    assert len({CONTEXT.rules, wishing("Ищу друзей").rules, wishing("Хочу танцевать").rules}) == 3
    assert wishing("Ищу друзей").rules == wishing("Ищу друзей").rules
