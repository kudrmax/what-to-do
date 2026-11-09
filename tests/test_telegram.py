from datetime import UTC, datetime

import httpx
import pytest
import respx

from tests.helpers import channel_page
from where_to_go.telegram import HtmlText, SourceError, TelegramChannelReader, TelegramHandle, TelegramPageParser
from selectolax.lexbor import LexborHTMLParser


@pytest.mark.parametrize(
    "link", ["https://t.me/afisha_bg", "t.me/s/afisha_bg", "@afisha_bg", "afisha_bg", "https://t.me/afisha_bg/123"]
)
def test_handle_is_taken_from_any_link_form(link):
    assert TelegramHandle.parse(link) == "afisha_bg"


def test_non_channel_link_is_rejected():
    with pytest.raises(SourceError):
        TelegramHandle.parse("https://example.com/events")


def test_post_text_keeps_line_breaks_and_link_targets():
    node = LexborHTMLParser('<div>Лекция<br/><b>в 19:00</b> <a href="https://reg.test/x">регистрация</a></div>').css_first("div")
    assert HtmlText.extract(node) == "Лекция\nв 19:00 регистрация (https://reg.test/x)"


def test_page_parser_reads_posts_with_images():
    page = TelegramPageParser(channel_page("bg", [(5, "2026-11-01T10:00:00+00:00", "Квиз в пятницу")]))
    [post] = page.posts()
    assert (post.external_id, post.url, post.text) == (5, "https://t.me/bg/5", "Квиз в пятницу")
    assert post.image_urls == ("https://cdn.test/5.jpg",)
    assert page.title() == "Канал bg"


@respx.mock
async def test_reader_pages_back_until_the_last_known_post():
    newest = [(i, f"2026-11-0{i - 10}T10:00:00+00:00", f"пост {i}") for i in (13, 14)]
    older = [(i, f"2026-11-0{i - 10}T10:00:00+00:00", f"пост {i}") for i in (11, 12)]
    respx.get("https://t.me/s/bg", params={"before": "13"}).respond(200, text=channel_page("bg", older))
    respx.get("https://t.me/s/bg").respond(200, text=channel_page("bg", newest, before=13))
    async with httpx.AsyncClient() as client:
        posts = await TelegramChannelReader(client).new_posts("bg", 11, datetime(2026, 10, 1, tzinfo=UTC))
    assert [p.external_id for p in posts] == [12, 13, 14]


@respx.mock
async def test_first_read_stops_at_the_history_limit():
    respx.get("https://t.me/s/bg").respond(
        200, text=channel_page("bg", [(1, "2026-09-01T10:00:00+00:00", "старый"), (2, "2026-11-05T10:00:00+00:00", "новый")], before=1)
    )
    async with httpx.AsyncClient() as client:
        posts = await TelegramChannelReader(client).new_posts("bg", None, datetime(2026, 10, 10, tzinfo=UTC))
    assert [p.external_id for p in posts] == [2]


@respx.mock
async def test_closed_channel_is_reported():
    respx.get("https://t.me/s/secret").respond(302, headers={"Location": "https://t.me/secret"})
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match="закрыт"):
            await TelegramChannelReader(client).new_posts("secret", None, datetime(2026, 10, 1, tzinfo=UTC))
