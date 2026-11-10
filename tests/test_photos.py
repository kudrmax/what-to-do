import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from tests.helpers import FakeLlm, channel_page, extraction_by_text, judge_same_titles, photos_saying, raw_event
from tests.test_pipeline import LATER, RECENT, FailingOnce, serve_channels
from where_to_go.container import Container
from where_to_go.db import Database
from where_to_go.images import ImageStore
from where_to_go.models import Post, Source
from where_to_go.photos import PhotoTranscriber
from where_to_go.refresh import Stage
from where_to_go.repositories import PhotoTextRepository
from where_to_go.settings import AppSettings, ClaudeModel


def store(*names: str) -> ImageStore:
    folder = Path(tempfile.mkdtemp())
    for name in names:
        (folder / name).write_bytes(name.encode())
    return ImageStore(folder, client=None)


def post(*images: str) -> Post:
    return Post(id=1, source_id=1, external_id=1, url="u", published_at=datetime(2026, 11, 9, tzinfo=UTC), text="t", image_paths=list(images))


def transcriber(llm, images: ImageStore, prompt: str = "Transcribe") -> tuple[PhotoTranscriber, PhotoTextRepository]:
    texts = PhotoTextRepository(Database(":memory:"))
    return PhotoTranscriber(llm, images, texts, lambda: prompt), texts


async def test_each_photo_goes_to_claude_after_its_numbered_caption_and_its_text_is_kept():
    llm = photos_saying("ВС, 22.11 | 18:00\nРАЗГОВОРНАЯ ЦЕРЕМОНИЯ", "poster of a tea ceremony")
    photos, texts = transcriber(llm, store("a.jpg", "b.png"))

    await photos.transcribe(["a.jpg", "b.png"])

    assert [(i.caption, i.media_type, i.data) for i in llm.images[0]] == [("Photo 0:", "image/jpeg", b"a.jpg"), ("Photo 1:", "image/png", b"b.png")]
    saved = texts.of(["a.jpg", "b.png"])
    assert saved["b.png"].text == "ВС, 22.11 | 18:00\nРАЗГОВОРНАЯ ЦЕРЕМОНИЯ" and saved["b.png"].shows == "poster of a tea ceremony"


async def test_a_photo_claude_skipped_or_got_wrong_stays_untranscribed():
    answer = {"photos": [{"photo": 0, "text": "", "shows": "people, no text"}, {"photo": 1, "text": 5}, {"photo": 9, "text": "", "shows": "x"}]}
    photos, texts = transcriber(FakeLlm(lambda *_: answer), store("a.jpg", "b.jpg"))

    await photos.transcribe(["a.jpg", "b.jpg"])

    assert set(texts.of(["a.jpg", "b.jpg"])) == {"a.jpg"}
    assert photos.untranscribed([post("a.jpg", "b.jpg")]) == ["b.jpg"]


def test_only_stored_photos_without_text_under_the_current_rules_are_untranscribed():
    photos, _ = transcriber(photos_saying(), store("a.jpg", "b.jpg"))
    assert photos.untranscribed([post("a.jpg", "gone.jpg"), post("a.jpg", "b.jpg")]) == ["a.jpg", "b.jpg"]


async def test_new_photo_rules_make_every_photo_untranscribed_again():
    images = store("a.jpg")
    texts = PhotoTextRepository(Database(":memory:"))
    prompt = ["Transcribe"]
    photos = PhotoTranscriber(photos_saying(), images, texts, lambda: prompt[0])
    await photos.transcribe(["a.jpg"])
    assert photos.untranscribed([post("a.jpg")]) == []

    prompt[0] = "Transcribe carefully"

    assert photos.untranscribed([post("a.jpg")]) == ["a.jpg"]


def test_at_most_ten_photos_of_a_post_are_read_in_batches():
    names = [f"{i}.jpg" for i in range(12)]
    photos, _ = transcriber(photos_saying(), store(*names))
    untranscribed = photos.untranscribed([post(*names)])
    assert len(untranscribed) == 10 and [len(b) for b in photos.batches(untranscribed)] == [7, 3]


async def test_the_schema_claude_gets_carries_the_field_descriptions():
    llm = photos_saying()
    photos, _ = transcriber(llm, store("a.jpg"))
    await photos.transcribe(["a.jpg"])
    item = llm.schemas[0]["$defs"]["PhotoReading"]["properties"]
    assert "word for word" in item["text"]["description"] and "table" in item["text"]["description"]


def test_photos_and_posts_are_read_by_sonnet_and_duplicates_merged_by_haiku_by_default():
    settings = AppSettings()
    assert (settings.photo_model, settings.extraction_model, settings.matching_model) == (ClaudeModel.SONNET, ClaudeModel.SONNET, ClaudeModel.HAIKU)


# ---------- in a refresh ----------


async def build(tmp_path, extraction, photo_llm):
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photo_llm, http=httpx.AsyncClient())
    city = container.cities.add("Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
    return container


def read_posts(extraction: FakeLlm) -> list[dict]:
    return [item for _, prompt in extraction.calls for item in json.loads(prompt.split("\n", 1)[1])]


@respx.mock
async def test_a_refresh_reads_each_post_with_the_text_of_its_photo_and_transcribes_it_once(tmp_path):
    extraction = extraction_by_text({"кафаны": [raw_event("Кафаны", "2026-11-13", photo=0)]})
    photo_llm = photos_saying("ПТ, 13.11 | 19:00 | КАФАНЫ", "poster of a lecture")
    container = await build(tmp_path, extraction, photo_llm)
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, LATER, "реклама")])

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE, progress.errors
    assert (progress.photos_to_read, progress.photos_read) == (2, 2)
    assert [item["photos"] for item in read_posts(extraction)] == [[{"index": 0, "shows": "poster of a lecture", "text": "ПТ, 13.11 | 19:00 | КАФАНЫ"}]] * 2
    assert all(images == [] for images in extraction.images)
    [card] = container.events.in_city(1)
    assert card.image_path is not None

    container.refresh.start()
    await container.refresh.wait()
    assert len(photo_llm.calls) == 1
    await container.close()


@respx.mock
async def test_a_post_whose_photo_claude_could_not_read_waits_for_the_next_refresh(tmp_path):
    extraction = extraction_by_text({"кафаны": [raw_event("Кафаны", "2026-11-13")]})
    container = await build(tmp_path, extraction, FailingOnce(photos_saying("КАФАНЫ")))
    serve_channels([(1, RECENT, "лекция про кафаны")], [])

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE and "фото" in progress.errors[0]
    assert extraction.calls == [] and container.events.in_city(1) == []

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.errors == [] and [item["photos"][0]["text"] for item in read_posts(extraction)] == ["КАФАНЫ"]
    assert len(container.events.in_city(1)) == 1
    await container.close()


@respx.mock
async def test_new_photo_rules_transcribe_the_photos_again_and_read_their_posts_again(tmp_path):
    extraction = extraction_by_text({"кафаны": [raw_event("Кафаны", "2026-11-13")]})
    photo_llm = photos_saying("КАФАНЫ")
    container = await build(tmp_path, extraction, photo_llm)
    serve_channels([(1, RECENT, "лекция про кафаны")], [])
    container.refresh.start()
    await container.refresh.wait()

    container.settings.update(photo_prompt="Transcribe every letter")
    container.refresh.start()
    progress = await container.refresh.wait()

    assert (progress.photos_read, progress.posts_read) == (1, 1)
    assert photo_llm.calls[-1][0] == "Transcribe every letter"
    await container.close()
