import gzip
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import httpx
import pytest
import respx

from tests.helpers import event_markup, event_page, sitemap, sitemap_index
from where_to_go.telegram import SourceError
from where_to_go.web import EventClock, EventMarkup, PageMeta, PageText, SiteAddress, SitemapReader, WebEventText, in_horizon

FIXTURES = Path(__file__).parent / "fixtures" / "web"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_polako_page_gives_its_event():
    event = EventMarkup.read(fixture("polako_event.html"))
    assert event.name == "Искусство быть нелепым"
    assert event.start_raw == "2026-11-18T19:00:00.000Z"
    assert (event.place, event.locality) == ("Restoran Tri", "Belgrade")
    assert event.address == "Светогорска, 46"
    assert event.organizer == "Event Catalog"
    assert event.image.startswith("https://polako.ams3.digitaloceanspaces.com/")
    assert event.description.startswith("«ИСКУССТВО БЫТЬ НЕЛЕПЫМ» от ČemoDan Theatre (https://www.instagram.com/")


@pytest.mark.parametrize("wrap", ["graph", "list", "type_list", "subtype"])
def test_event_is_found_however_it_is_wrapped(wrap):
    event = EventMarkup.read(event_page(event_markup(wrap, name="Джаз")))
    assert event is not None and event.name == "Джаз"


def test_date_only_start_stays_a_date():
    assert EventMarkup.read(event_page(startDate="2026-11-20")).start == date(2026, 11, 20)


def test_page_without_event_markup_gives_none():
    assert EventMarkup.read(event_page(markup=False)) is None


def test_event_without_start_is_not_an_event():
    assert EventMarkup.read(event_page(startDate=None)) is None


def test_image_and_price_come_in_any_shape():
    event = EventMarkup.read(
        event_page(image=[{"@type": "ImageObject", "url": "https://cdn.test/a.jpg"}], offers=[{"@type": "Offer", "price": 1500, "priceCurrency": "RSD"}])
    )
    assert event.image == "https://cdn.test/a.jpg"
    assert event.price == "1500 RSD"
    assert EventMarkup.read(event_page(offers={"@type": "AggregateOffer", "lowPrice": "800", "priceCurrency": "RSD"})).price == "от 800 RSD"


def test_page_text_is_the_main_part_without_markup():
    html = event_page(text="Начало в 19:00")
    assert PageText.main(html) == "Страница\nНачало в 19:00"
    assert PageMeta.site_name(html) == "Сайт афиши"


def test_site_address_takes_the_section_of_the_link():
    assert SiteAddress.parse("https://x.club/ru/events/a-2026-11-18-1?utm=1") == ("https://x.club", "/ru/events/")
    assert SiteAddress.parse("x.club/ru/events/a") == ("https://x.club", "/ru/events/")


@pytest.mark.parametrize("link", ["https://x.club", "https://x.club/", "ftp://x.club/a/b", "просто текст"])
def test_link_without_a_page_is_refused(link):
    with pytest.raises(SourceError, match="ссылку на страницу события"):
        SiteAddress.parse(link)


@respx.mock
async def test_sitemap_index_and_gzip_are_followed():
    respx.get("https://site.test/robots.txt").respond(200, text="User-agent: *\nDisallow: /api/*\nSitemap: https://site.test/index.xml\n")
    respx.get("https://site.test/index.xml").respond(200, text=sitemap_index(["https://site.test/a.xml", "https://site.test/b.xml.gz"]))
    respx.get("https://site.test/a.xml").respond(200, text=sitemap(["https://site.test/1", "https://site.test/2"]))
    respx.get("https://site.test/b.xml.gz").respond(200, content=gzip.compress(sitemap(["https://site.test/3", "https://site.test/1"]).encode()))
    async with httpx.AsyncClient() as client:
        reader = SitemapReader(client)
        located = await reader.locate("https://site.test")
        assert located == ["https://site.test/index.xml"]
        assert await reader.urls(located) == ["https://site.test/1", "https://site.test/2", "https://site.test/3"]


@respx.mock
async def test_sitemap_xml_is_tried_when_robots_names_none():
    respx.get("https://site.test/robots.txt").respond(200, text="User-agent: *\n")
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap(["https://site.test/1"]))
    async with httpx.AsyncClient() as client:
        assert await SitemapReader(client).locate("https://site.test") == ["https://site.test/sitemap.xml"]


@respx.mock
async def test_site_without_sitemap_is_refused():
    respx.get("https://site.test/robots.txt").respond(404)
    respx.get("https://site.test/sitemap.xml").respond(404)
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match=r"На сайте нет списка страниц \(sitemap\)"):
            await SitemapReader(client).locate("https://site.test")


BELGRADE = ZoneInfo("Europe/Belgrade")


def test_polako_utc_label_is_local_time():
    html = fixture("polako_event.html")
    event = EventMarkup.read(html)
    assert EventClock.detect(event, PageText.main(html), BELGRADE) is True
    assert EventClock(True, BELGRADE).local(event.start) == datetime(2026, 11, 18, 19, 0)


def test_honest_utc_is_detected_and_converted():
    event = EventMarkup.read(event_page(startDate="2026-11-20T18:00:00Z"))
    assert EventClock.detect(event, "Начало в 19:00", BELGRADE) is False
    assert EventClock(False, BELGRADE).local(event.start) == datetime(2026, 11, 20, 19, 0)


def test_honest_offset_is_converted():
    start = datetime(2026, 11, 26, 18, 0, tzinfo=timezone(timedelta(hours=1)))
    assert EventClock(False, BELGRADE).local(start) == datetime(2026, 11, 26, 18, 0)


def test_time_with_real_offset_needs_no_check():
    event = EventMarkup.read(event_page(startDate="2026-11-20T19:00:00+01:00"))
    assert EventClock.detect(event, "19:00", BELGRADE) is None


def test_date_stays_a_date():
    assert EventClock(True, BELGRADE).local(date(2026, 11, 20)) == date(2026, 11, 20)


def test_unclear_votes_trust_the_offset():
    assert EventClock.decide([None, None]) is False
    assert EventClock.decide([True, False]) is False
    assert EventClock.decide([True, None]) is True


def test_running_exhibition_is_in_horizon():
    today = date(2026, 11, 15)
    assert in_horizon(date(2026, 11, 1), date(2026, 11, 30), today, 30)
    assert in_horizon(datetime(2026, 12, 15, 19, 0), None, today, 30)
    assert not in_horizon(date(2026, 12, 20), None, today, 30)
    assert not in_horizon(datetime(2026, 11, 14, 19, 0), None, today, 30)


def test_text_for_claude_has_facts_not_html():
    text = WebEventText.render(EventMarkup.read(fixture("polako_event.html")), EventClock(True, BELGRADE), "")
    assert text.splitlines()[:6] == [
        "Искусство быть нелепым",
        "Начало: 2026-11-18 19:00",
        "Конец: 2026-11-18 21:00",
        "Место: Restoran Tri, Светогорска, 46, Belgrade",
        "Организатор: Event Catalog",
        "",
    ]
    assert "<" not in text
    assert "Курс клоунады для взрослых" in text


def test_lines_without_value_are_left_out():
    event = EventMarkup.read(event_page(startDate="2026-11-20", location=None, offers={"price": 0, "priceCurrency": "RSD"}))
    assert WebEventText.render(event, EventClock(False, BELGRADE), "").splitlines()[:3] == ["Концерт", "Начало: 2026-11-20", "Цена: 0 RSD"]


def test_short_description_is_completed_with_page_text():
    event = EventMarkup.read(event_page(description="Коротко."))
    text = WebEventText.render(event, EventClock(False, BELGRADE), "Полный текст страницы " * 300)
    assert "Коротко." in text and "Полный текст страницы" in text
    assert len(text) < 3400


def test_place_repeated_in_every_field_is_said_once():
    event = EventMarkup.read(event_page(location={"name": "Belgrade", "address": {"streetAddress": "Belgrade", "addressLocality": "Belgrade"}}))
    assert "Место: Belgrade\n" in WebEventText.render(event, EventClock(False, BELGRADE), "")


@respx.mock
async def test_one_dead_nested_sitemap_does_not_lose_the_others():
    respx.get("https://site.test/index.xml").respond(200, text=sitemap_index(["https://site.test/blog.xml", "https://site.test/events.xml"]))
    respx.get("https://site.test/blog.xml").respond(404)
    respx.get("https://site.test/events.xml").respond(200, text=sitemap(["https://site.test/ru/events/1"]))
    async with httpx.AsyncClient() as client:
        assert await SitemapReader(client).urls(["https://site.test/index.xml"]) == ["https://site.test/ru/events/1"]


@respx.mock
async def test_dead_top_sitemap_is_the_error():
    respx.get("https://site.test/sitemap.xml").respond(503)
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError):
            await SitemapReader(client).urls(["https://site.test/sitemap.xml"])


@respx.mock
async def test_broken_gzip_is_a_source_error_not_a_crash():
    respx.get("https://site.test/sitemap.xml").respond(200, content=b"\x1f\x8b broken")
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError):
            await SitemapReader(client).urls(["https://site.test/sitemap.xml"])


@respx.mock
async def test_every_sitemap_robots_names_is_found():
    respx.get("https://site.test/robots.txt").respond(200, text="Sitemap: https://site.test/pages.xml\nSitemap: https://site.test/events.xml\n")
    async with httpx.AsyncClient() as client:
        assert await SitemapReader(client).locate("https://site.test") == ["https://site.test/pages.xml", "https://site.test/events.xml"]


def test_dated_folders_are_not_part_of_the_section():
    assert SiteAddress.parse("https://x.club/events/2026/11/concert") == ("https://x.club", "/events/")


@pytest.mark.parametrize("link", ["https://x.club/slug", "https://x.club/event.php?id=5", "https://x.club/2026/11/slug"])
def test_link_whose_section_is_the_whole_site_is_refused(link):
    with pytest.raises(SourceError, match="весь сайт"):
        SiteAddress.parse(link)


@pytest.mark.parametrize("raw", ["2026-11-20+01:00", "20261120"])
def test_date_without_time_never_gets_a_made_up_time(raw):
    start = EventMarkup.read(event_page(startDate=raw)).start
    assert start == date(2026, 11, 20)


def test_event_inside_a_page_main_entity_is_found():
    page = {"@context": "https://schema.org", "@type": "WebPage", "mainEntity": event_markup(name="Внутри страницы")}
    assert EventMarkup.read(event_page(page)).name == "Внутри страницы"


def test_markdown_description_reads_as_plain_text():
    description = "# Заголовок\n\nТекст **жирный** и *курсив*, [Новости](https://t.me/news).\n\n- пункт"
    event = EventMarkup.read(event_page(description=description))
    assert event.description == "Заголовок\n\nТекст жирный и курсив, Новости (https://t.me/news).\n\n- пункт"


def test_html_description_reads_as_plain_text():
    event = EventMarkup.read(event_page(description="<p>Первый <b>абзац</b></p><p>Второй <a href='https://x.test'>ссылка</a></p>"))
    assert event.description == "Первый абзац\n\nВторой ссылка (https://x.test)"
