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
        posts = await TelegramChannelReader(client).new_posts("bg", 11, first_read_limit=1)
    assert [p.external_id for p in posts] == [12, 13, 14]


@respx.mock
async def test_first_read_takes_the_last_n_posts_paging_back_as_needed():
    at = "2026-11-05T10:00:00+00:00"
    older = respx.get("https://t.me/s/bg", params={"before": "4"}).respond(200, text=channel_page("bg", [(i, at, f"пост {i}") for i in (1, 2, 3)], before=1))
    respx.get("https://t.me/s/bg").respond(200, text=channel_page("bg", [(i, at, f"пост {i}") for i in (4, 5)], before=4))
    async with httpx.AsyncClient() as client:
        reader = TelegramChannelReader(client)
        assert [p.external_id for p in await reader.new_posts("bg", None, first_read_limit=2)] == [4, 5]
        assert not older.called
        assert [p.external_id for p in await reader.new_posts("bg", None, first_read_limit=4)] == [2, 3, 4, 5]
        assert older.call_count == 1


@respx.mock
async def test_closed_channel_is_reported():
    respx.get("https://t.me/s/secret").respond(302, headers={"Location": "https://t.me/secret"})
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match="закрыт"):
            await TelegramChannelReader(client).new_posts("secret", None, first_read_limit=20)
