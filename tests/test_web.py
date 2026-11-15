import gzip
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from tests.helpers import event_markup, event_page, sitemap, sitemap_index
from where_to_go.telegram import SourceError
from where_to_go.web import EventMarkup, PageMeta, PageText, SiteAddress, SitemapReader

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
    assert event.description.startswith("# «ИСКУССТВО БЫТЬ НЕЛЕПЫМ»")


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
        assert located == "https://site.test/index.xml"
        assert await reader.urls(located) == ["https://site.test/1", "https://site.test/2", "https://site.test/3"]


@respx.mock
async def test_sitemap_xml_is_tried_when_robots_names_none():
    respx.get("https://site.test/robots.txt").respond(200, text="User-agent: *\n")
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap(["https://site.test/1"]))
    async with httpx.AsyncClient() as client:
        assert await SitemapReader(client).locate("https://site.test") == "https://site.test/sitemap.xml"


@respx.mock
async def test_site_without_sitemap_is_refused():
    respx.get("https://site.test/robots.txt").respond(404)
    respx.get("https://site.test/sitemap.xml").respond(404)
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match=r"На сайте нет списка страниц \(sitemap\)"):
            await SitemapReader(client).locate("https://site.test")
