"""Cities away from Belgrade: on UTC, behind it, and across a daylight saving change."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from tests.helpers import add_city, event_page, sitemap
from where_to_go.calendar_file import EventCalendarFile
from where_to_go.container import Container
from where_to_go.extraction import PostExtractor
from where_to_go.localities import LocalityJudge, LocalityRepository
from where_to_go.models import City, Event, EventKind, Post, Source, SourceKind
from where_to_go.web import EventClock, EventMarkup, SitemapReader
from where_to_go.web_sources import WebSiteProbe, WebSiteReader

LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
WINTER = datetime(2026, 11, 16, 12, tzinfo=UTC)
SECTION = "https://site.test/events/"


def serve(pages: dict[str, str]) -> dict:
    respx.get("https://site.test/robots.txt").respond(200, text="Sitemap: https://site.test/sitemap.xml\n")
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap([SECTION + name for name in pages]))
    return {name: respx.get(SECTION + name).respond(200, text=html) for name, html in pages.items()}


def labelled_utc(day: str, at: str, shown: str) -> str:
    return event_page(startDate=f"{day}T{at}:00Z", name=day, text=f"Doors at {shown}")


class NoTowns:
    async def complete_json(self, *_):
        return {"places": []}


@respx.mock
async def test_a_london_site_added_in_winter_leaves_its_time_labels_open_and_a_summer_page_settles_them(tmp_path):
    """In winter London is on UTC: a page shows 19:00 whether the site means UTC or local time."""
    serve({"a": labelled_utc("2026-11-20", "19:00", "19:00"), "b": labelled_utc("2026-11-27", "19:00", "19:00")})
    async with httpx.AsyncClient() as client:
        _, site = await WebSiteProbe(client, SitemapReader(client), clock=lambda: WINTER).probe(SECTION + "a", LONDON)
    assert (site.times_are_local, site.times_settled) == (False, False)

    container = Container.build(tmp_path)
    city = add_city(container, "London", "Europe/London", country="United Kingdom", language="English")
    source = container.sources.add(Source(city_id=city.id, kind=SourceKind.WEB, handle="site.test/events/", title="Site"))
    site.source_id = source.id
    container.web.add_site(site)
    serve({"a": labelled_utc("2026-11-20", "19:00", "19:00"), "summer": labelled_utc("2027-06-10", "19:00", "19:00")})
    async with httpx.AsyncClient() as client:
        reader = WebSiteReader(client, SitemapReader(client), container.web, container.posts, LocalityJudge(NoTowns(), LocalityRepository(container.db)), clock=lambda: WINTER)
        await reader.collect(container.sources.get(source.id), city)

    settled = container.web.site(source.id)
    assert (settled.times_are_local, settled.times_settled) == (True, True)
    summer = container.web.pages(source.id)[SECTION + "summer"]
    assert summer.start_time == time(19, 0)  # not 20:00, which reading «19:00Z» as UTC in British Summer Time gives
    await container.close()


@respx.mock
async def test_a_london_site_with_honest_utc_settles_on_the_offset_in_summer(tmp_path):
    container = Container.build(tmp_path)
    city = add_city(container, "London", "Europe/London", country="United Kingdom", language="English")
    source = container.sources.add(Source(city_id=city.id, kind=SourceKind.WEB, handle="site.test/events/", title="Site"))
    from where_to_go.models import WebSite

    container.web.add_site(WebSite(source_id=source.id, sitemap_urls=["https://site.test/sitemap.xml"], prefix=SECTION, times_settled=False))
    serve({"summer": labelled_utc("2027-06-10", "18:00", "19:00")})
    async with httpx.AsyncClient() as client:
        reader = WebSiteReader(client, SitemapReader(client), container.web, container.posts, LocalityJudge(NoTowns(), LocalityRepository(container.db)), clock=lambda: WINTER)
        await reader.collect(container.sources.get(source.id), city)
    site = container.web.site(source.id)
    assert (site.times_are_local, site.times_settled) == (False, True)
    assert container.web.pages(source.id)[SECTION + "summer"].start_time == time(19, 0)
    await container.close()


def test_an_undecided_site_keeps_waiting_while_pages_tell_nothing():
    assert EventClock.settled([None, None]) is False
    assert EventClock.settled([None, False]) is True


def test_a_new_york_evening_in_utc_lands_on_the_new_york_day():
    """20 November 00:00 UTC is still 19 November in New York: the card goes on the 19th."""
    event = EventMarkup.read(event_page(startDate="2026-11-20T00:00:00Z", text="7 pm"))
    assert EventClock(False, NEW_YORK).local(event.start) == datetime(2026, 11, 19, 19, 0)


@pytest.mark.parametrize(
    "published,shown",
    [
        (datetime(2026, 11, 1, 3, 30, tzinfo=UTC), "2026-10-31 23:30 (Saturday)"),  # still EDT, UTC-4
        (datetime(2026, 11, 1, 7, 30, tzinfo=UTC), "2026-11-01 02:30 (Sunday)"),  # EST from 2:00, UTC-5
        (datetime(2027, 3, 14, 7, 30, tzinfo=UTC), "2027-03-14 03:30 (Sunday)"),  # EDT again
    ],
)
def test_claude_reads_publication_times_in_new_york_time_across_daylight_saving(published, shown):
    city = City(id=1, name="New York", country="United States", timezone="America/New_York", card_language="English")
    post = Post(id=1, source_id=1, external_id=1, url="https://t.me/nyc/1", published_at=published, text="x")
    prompt = PostExtractor._prompt([_photos(post)], {1: Source(id=1, city_id=1, handle="nyc", title="NYC")}, city)
    assert f'"published": "{shown}"' in prompt


def _photos(post):
    from where_to_go.extraction import PostPhotos

    return PostPhotos(post, {})


@pytest.mark.parametrize("day,offset", [(date(2027, 1, 15), -5), (date(2027, 3, 14), -4), (date(2027, 7, 4), -4), (date(2026, 11, 1), -5)])
def test_a_new_york_calendar_entry_keeps_its_wall_clock_on_both_sides_of_daylight_saving(day, offset):
    import icalendar

    city = City(id=1, name="New York", country="United States", timezone="America/New_York", card_language="English")
    event = Event(id=1, city_id=1, title="Show", original_title="Show", description="", kind=EventKind.SINGLE, start_date=day, start_time=time(19, 0), venue="Joe's Pub")
    entry = icalendar.Calendar.from_ical(EventCalendarFile(event, city, None).render()).walk("VEVENT")[0]
    start = entry.decoded("dtstart")
    assert (start.hour, start.utcoffset()) == (19, timedelta(hours=offset))
    assert str(entry["location"]) == "Joe's Pub, New York, United States"
