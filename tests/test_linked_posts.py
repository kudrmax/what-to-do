from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx

from tests.helpers import add_city, channel_page, extraction_by_text, judge_same_titles, photos_saying, raw_event
from where_to_go.container import Container
from where_to_go.linked_posts import LinkedPosts
from where_to_go.models import CollectedPost, EventFacts, EventKind, Mark, Source, SourceKind, TelegramPostLink
from where_to_go.refresh import Stage

RECENT = (datetime.now(UTC) - timedelta(days=1)).isoformat()
LONG_AGO = (datetime.now(UTC) - timedelta(days=60)).isoformat()

DIGEST = (
    "Афиша недели: импро (https://t.me/afisha/3), "
    "умная среда (https://t.me/umnaya/638), реклама канала (https://t.me/afisha)"
)
IMPRO = "Каждую субботу импровизация с Ниной, прошлый сезон тут: https://t.me/afisha/1"
LECTURE = "Умная среда: быть блогером в эмиграции"


@pytest.fixture
async def app(tmp_path):
    extraction = extraction_by_text(
        {
            "Афиша недели": [
                raw_event("Импро", "2026-11-21", "13:00", details_url="https://t.me/afisha/3"),
                raw_event("Блогер", "2026-11-18", "19:00", details_url="https://t.me/umnaya/638"),
            ],
            "Каждую субботу": [raw_event("Импровизационные игры с Ниной", "2026-11-07", "13:00", kind="recurring", rrule="FREQ=WEEKLY;BYDAY=SA")],
            "Умная среда": [raw_event("Быть блогером в эмиграции", "2026-11-18", "19:00")],
        }
    )
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    city = add_city(container, "Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
    yield container, extraction
    await container.close()


def serve():
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"img", headers={"content-type": "image/jpeg"})
    deeper = respx.get("https://t.me/s/afisha", params={"before": "2"}).respond(200, text=channel_page("afisha", []))
    respx.get("https://t.me/s/afisha", params={"before": "4"}).respond(200, text=channel_page("afisha", [(2, LONG_AGO, "старое"), (3, LONG_AGO, IMPRO)], before=2))
    respx.get("https://t.me/s/umnaya", params={"before": "639"}).respond(200, text=channel_page("umnaya", [(638, RECENT, LECTURE)]))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(7, RECENT, DIGEST)]))
    return deeper


@respx.mock
async def test_a_digest_line_and_the_post_it_links_to_make_one_card(app):
    container, _ = app
    deeper = serve()

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE, progress.errors
    cards = {e.title: e for e in container.events.in_city(1)}
    assert set(cards) == {"Импровизационные игры с Ниной", "Быть блогером в эмиграции"}
    impro = cards["Импровизационные игры с Ниной"]
    assert impro.kind is EventKind.RECURRING
    assert {m.post_url for m in container.mentions.of_event(impro.id)} == {"https://t.me/afisha/7", "https://t.me/afisha/3"}
    lecture = cards["Быть блогером в эмиграции"]
    assert {m.post_url for m in container.mentions.of_event(lecture.id)} == {"https://t.me/afisha/7", "https://t.me/umnaya/638"}
    assert not deeper.called  # a linked post's own links are not followed


@respx.mock
async def test_linked_posts_are_fetched_and_read_once(app):
    container, extraction = app
    serve()
    container.refresh.start()
    await container.refresh.wait()
    calls = len(extraction.calls)

    container.refresh.start()
    await container.refresh.wait()

    assert len(extraction.calls) == calls
    assert len(container.events.in_city(1)) == 2


@respx.mock
async def test_a_linked_channel_post_already_collected_is_not_fetched_again(app):
    container, _ = app
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"img", headers={"content-type": "image/jpeg"})
    old = respx.get("https://t.me/s/afisha", params={"before": "4"}).respond(200, text=channel_page("afisha", []))
    respx.get("https://t.me/s/umnaya", params={"before": "639"}).respond(200, text=channel_page("umnaya", [(638, RECENT, LECTURE)]))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(3, RECENT, IMPRO), (7, RECENT, DIGEST)]))

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE, progress.errors
    assert not old.called
    assert len(container.events.in_city(1)) == 2


@respx.mock
async def test_a_link_to_a_closed_channel_does_not_stop_the_refresh(app):
    container, _ = app
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"img", headers={"content-type": "image/jpeg"})
    respx.get("https://t.me/s/afisha", params={"before": "4"}).respond(200, text=channel_page("afisha", [(3, LONG_AGO, IMPRO)]))
    respx.get("https://t.me/s/umnaya", params={"before": "639"}).respond(302)
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(7, RECENT, DIGEST)]))

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE and progress.errors == []
    assert {e.title for e in container.events.in_city(1)} == {"Импровизационные игры с Ниной", "Блогер"}


@pytest.mark.parametrize(
    "text,links",
    [
        ("импро (https://t.me/afisha/3) и t.me/Umnaya_sreda/638.", [("afisha", 3), ("Umnaya_sreda", 638)]),
        ("канал https://t.me/afisha, превью t.me/s/afisha/5, приватный t.me/c/123/4, комментарий t.me/afisha/3/9", []),
        ("дважды https://t.me/afisha/3 и https://t.me/afisha/3", [("afisha", 3)]),
    ],
)
def test_post_links_are_found_in_text(text, links):
    assert [(link.handle, link.number) for link in TelegramPostLink.all_in(text)] == links


def test_a_link_has_one_key_whatever_the_case():
    assert TelegramPostLink.parse("https://t.me/Afisha/3").key == TelegramPostLink.parse("t.me/afisha/3").key


@pytest.mark.parametrize(
    "facts,day,expected",
    [
        (dict(kind=EventKind.RECURRING, start_date=date(2026, 11, 7), rrule="FREQ=WEEKLY;BYDAY=SA"), date(2026, 11, 21), True),
        (dict(kind=EventKind.RECURRING, start_date=date(2026, 11, 7), rrule="FREQ=WEEKLY;BYDAY=SA"), date(2026, 11, 20), False),
        (dict(kind=EventKind.MULTIDAY, start_date=date(2026, 11, 1), end_date=date(2026, 11, 30)), date(2026, 11, 21), True),
        (dict(kind=EventKind.SINGLE, start_date=date(2026, 11, 21)), date(2026, 11, 21), True),
        (dict(kind=EventKind.SINGLE, start_date=date(2026, 11, 21)), date(2026, 11, 22), False),
    ],
)
def test_an_event_knows_the_days_it_happens_on(facts, day, expected):
    assert EventFacts(title="x", original_title="x", description="", **facts).happens_on(day) is expected


@respx.mock
async def test_a_line_carded_before_its_post_was_fetched_moves_to_the_post_card_unless_marked(app):
    container, _ = app
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"img", headers={"content-type": "image/jpeg"})
    closed = respx.get("https://t.me/s/afisha", params={"before": "4"}).respond(302)
    respx.get("https://t.me/s/umnaya", params={"before": "639"}).respond(302)
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(7, RECENT, DIGEST)]))
    container.refresh.start()
    await container.refresh.wait()
    blogger = next(e for e in container.events.in_city(1) if e.title == "Блогер")
    container.events.set_mark(blogger.id, Mark(interest=5))

    closed.respond(200, text=channel_page("afisha", [(3, LONG_AGO, IMPRO)]))
    respx.get("https://t.me/s/umnaya", params={"before": "639"}).respond(200, text=channel_page("umnaya", [(638, RECENT, LECTURE)]))
    container.posts.mark_processed(container.posts.id_of(1, 7), "older rules")
    container.refresh.start()
    await container.refresh.wait()

    titles = sorted(e.title for e in container.events.in_city(1))
    assert titles == ["Блогер", "Быть блогером в эмиграции", "Импровизационные игры с Ниной"]  # the rated line stays put


class _RecordingReader:
    def __init__(self) -> None:
        self.asked: list[str] = []

    async def posts(self, handle: str, numbers: set[int]) -> list:
        self.asked.append(handle)
        return []


async def test_an_instagram_caption_linking_a_telegram_post_does_not_lead_on(app):
    container, _ = app
    profile = container.sources.add(Source(city_id=1, kind=SourceKind.INSTAGRAM, handle="eje.belgrade", title="Eje"))
    caption = CollectedPost(external_id=1, url="https://www.instagram.com/p/a/", published_at=datetime.now(UTC), text=DIGEST)
    container.posts.add_new(profile.id, caption, [])
    reader = _RecordingReader()

    added = await LinkedPosts(container.posts, reader, container.images).collect(
        [container.posts.get(container.posts.id_of(profile.id, 1))], container.sources.in_city(1)
    )

    assert added == 0 and reader.asked == []
