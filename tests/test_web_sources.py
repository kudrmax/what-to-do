import json
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from tests.helpers import FakeLlm, event_page, raw_event, sitemap

from where_to_go.container import Container
from where_to_go.models import CollectedPost, ExtractedEvent, Mention, Source, SourceKind, SourcePublic, WebPage, WebSite
from where_to_go.reading_rules import ReadingRules
from where_to_go.telegram import SourceError
from where_to_go.web import SitemapReader
from where_to_go.localities import LocalityJudge, LocalityRepository
from where_to_go.llm import LlmError
from where_to_go.web_sources import PageFetcher, WebSiteProbe, WebSiteReader

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
async def app(tmp_path):
    container = Container.build(tmp_path)
    city = container.cities.add("Белград", "Europe/Belgrade")
    yield container, city
    await container.close()


def add_site(container, city, handle="site.test/ru/events/") -> Source:
    source = container.sources.add(Source(city_id=city.id, kind=SourceKind.WEB, handle=handle, title="Сайт"))
    container.web.add_site(WebSite(source_id=source.id, sitemap_urls=["https://site.test/sitemap.xml"], prefix="https://site.test/ru/events/"))
    return source


def add_post(container, source, external_id=1, text="факты") -> int:
    container.posts.add_new(source.id, CollectedPost(external_id=external_id, url="https://site.test/ru/events/a", published_at=NOW, text=text), [])
    return next(p.id for p in container.posts.unprocessed([source.id]) if p.external_id == external_id)


async def test_web_source_url_is_its_section(app):
    container, city = app
    source = add_site(container, city)
    assert SourcePublic.model_validate(source, from_attributes=True).url == "https://site.test/ru/events/"


async def test_deleting_web_source_removes_its_site_and_pages(app):
    container, city = app
    source = add_site(container, city)
    container.web.save_page(WebPage(source_id=source.id, url="https://site.test/ru/events/a", is_event=False, found_at=NOW, checked_at=NOW))
    container.catalog.delete(source.id)
    with pytest.raises(KeyError):
        container.web.site(source.id)
    assert container.web.pages(source.id) == {}


async def test_web_posts_are_not_reread_by_recent_rule(app):
    container, city = app
    source = add_site(container, city)
    post_id = add_post(container, source)
    container.posts.mark_processed(post_id, "old rules")
    assert container.posts.to_read([source.id], ReadingRules.POSTS, 20) == []


async def test_changed_page_is_read_again(app):
    container, city = app
    source = add_site(container, city)
    post_id = add_post(container, source)
    container.posts.mark_processed(post_id, ReadingRules.POSTS)
    container.posts.replace_text(post_id, "новые факты")
    post = container.posts.get(post_id)
    assert (post.text, post.processed_at) == ("новые факты", None)


async def test_changed_page_is_not_reread_when_user_merged_it(app):
    container, city = app
    source = add_site(container, city)
    post_id = add_post(container, source)
    container.posts.mark_processed(post_id, ReadingRules.POSTS)
    with container.db.session() as s:
        s.add(Mention(post_id=post_id, item_index=0, data=ExtractedEvent.model_validate(raw_event("x", "2026-11-20")), locked=True))
        s.commit()
    container.posts.replace_text(post_id, "новые факты")
    assert container.posts.get(post_id).text == "факты"


SECTION = "https://site.test/ru/events/"
BELGRADE = ZoneInfo("Europe/Belgrade")


def page_url(name: str) -> str:
    return SECTION + name


def serve_site(pages: dict[str, str], others: tuple[str, ...] = ("https://site.test/ru/news/1", "https://site.test/en/events/x")):
    respx.get("https://site.test/robots.txt").respond(200, text="Sitemap: https://site.test/sitemap.xml\n")
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap([*others, *(page_url(n) for n in pages)]))
    return {name: respx.get(page_url(name)).respond(200, text=html) for name, html in pages.items()}


def on(day: str, at: str = "19:00", **fields) -> str:
    return event_page(startDate=f"{day}T{at}:00.000Z", name=fields.pop("name", day), text=f"Начало в {at}", **fields)


@respx.mock
async def test_probe_finds_section_and_examples():
    serve_site({f"e{i}": on(f"2026-11-{16 + i}") for i in range(5)})
    async with httpx.AsyncClient() as client:
        preview, site = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("e0"), BELGRADE)
    assert (preview.kind, preview.title, preview.handle, preview.pages_found) == (SourceKind.WEB, "Сайт афиши", "site.test/ru/events/", 5)
    assert [(e.title, e.day, e.time) for e in preview.examples] == [("2026-11-16", date(2026, 11, 16), "19:00"), ("2026-11-17", date(2026, 11, 17), "19:00"), ("2026-11-18", date(2026, 11, 18), "19:00")]
    assert (site.sitemap_urls, site.prefix) == (["https://site.test/sitemap.xml"], SECTION)


@respx.mock
async def test_probe_detects_local_time_labelled_utc():
    serve_site({"a": on("2026-11-16"), "b": on("2026-11-17")})
    async with httpx.AsyncClient() as client:
        _, site = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)
    assert site.times_are_local is True


@respx.mock
async def test_probe_believes_an_honest_offset():
    serve_site({"a": event_page(startDate="2026-11-16T18:00:00Z", text="Начало в 19:00")})
    async with httpx.AsyncClient() as client:
        _, site = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)
    assert site.times_are_local is False


@respx.mock
async def test_probe_refuses_page_without_event():
    serve_site({"a": event_page(markup=False)})
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match="На странице нет разметки события"):
            await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)


@respx.mock
async def test_probe_refuses_site_without_sitemap():
    respx.get(page_url("a")).respond(200, text=on("2026-11-16"))
    respx.get("https://site.test/robots.txt").respond(404)
    respx.get("https://site.test/sitemap.xml").respond(404)
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match=r"sitemap"):
            await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)


@respx.mock
async def test_probe_says_when_site_does_not_answer():
    respx.get(page_url("a")).mock(side_effect=httpx.ConnectError("down"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match="Страница по ссылке не открывается"):
            await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)


@pytest.fixture
async def reading(app):
    container, city = app
    source = container.sources.add(Source(city_id=city.id, kind=SourceKind.WEB, handle="site.test/ru/events/", title="Сайт"))
    container.web.add_site(WebSite(source_id=source.id, sitemap_urls=["https://site.test/sitemap.xml"], prefix=SECTION, times_are_local=True))
    client = httpx.AsyncClient()
    now = [NOW]

    judge = FakeLlm(lambda _, prompt: {"places": [{"name": n, "in_city": n in ("Belgrade", "Београд")} for n in json.loads(prompt)["names"]]})
    localities = LocalityJudge(judge, LocalityRepository(container.db))

    def reader() -> WebSiteReader:
        return WebSiteReader(client, SitemapReader(client), container.web, container.posts, localities, clock=lambda: now[0])

    async def collect():
        posts = await reader().collect(container.sources.get(source.id), city)
        for post in posts:
            container.posts.add_new(source.id, post, [])
        return posts

    collect.judge = judge
    yield container, source, collect, now
    await client.aclose()


@respx.mock
async def test_first_collect_reads_every_page_but_posts_only_horizon(reading):
    container, source, collect, _ = reading
    routes = serve_site({"soon": on("2026-11-25", name="Скоро"), "later": on("2027-01-14", name="Потом"), "category": event_page(markup=False)})
    posts = await collect()
    assert [p.text.splitlines()[:2] for p in posts] == [["Скоро", "Начало: 2026-11-25 19:00"]]
    assert posts[0].url == page_url("soon") and posts[0].image_urls == ["https://cdn.test/poster.jpg"]
    assert await collect() == []
    assert [r.call_count for r in routes.values()] == [1, 1, 1]


@respx.mock
async def test_page_entering_horizon_becomes_post_without_download(reading):
    container, source, collect, now = reading
    routes = serve_site({"later": on("2027-01-14", name="Потом")})
    assert await collect() == []
    now[0] = NOW + timedelta(days=40)
    assert [p.text.splitlines()[0] for p in await collect()] == ["Потом"]
    assert routes["later"].call_count == 1


@respx.mock
async def test_upcoming_week_is_rechecked_and_change_rereads_post(reading):
    container, source, collect, now = reading
    routes = serve_site({"soon": on("2026-11-18", name="Скоро"), "month": on("2026-12-01", name="Через две недели")})
    await collect()
    for post in container.posts.unprocessed([source.id]):
        container.posts.mark_processed(post.id, ReadingRules.POSTS)
    routes["soon"].respond(200, text=on("2026-11-19", name="Скоро"))
    now[0] = NOW + timedelta(days=1)
    assert await collect() == []
    assert (routes["soon"].call_count, routes["month"].call_count) == (2, 1)
    [changed] = container.posts.unprocessed([source.id])
    assert "Начало: 2026-11-19 19:00" in changed.text


@respx.mock
async def test_broken_page_does_not_fail_source(reading):
    container, source, collect, _ = reading
    serve_site({"ok": on("2026-11-20", name="Работает")})
    respx.get(page_url("broken")).respond(500)
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap([page_url("broken"), page_url("ok")]))
    assert [p.text.splitlines()[0] for p in await collect()] == ["Работает"]
    assert page_url("broken") not in container.web.pages(source.id)


@respx.mock
async def test_running_exhibition_is_collected(reading):
    container, source, collect, _ = reading
    serve_site({"expo": on("2026-11-01", name="Выставка", endDate="2026-11-30T20:00:00.000Z")})
    assert [p.text.splitlines()[0] for p in await collect()] == ["Выставка"]


@respx.mock
async def test_broken_sitemap_is_the_source_error(reading):
    container, source, collect, _ = reading
    respx.get("https://site.test/sitemap.xml").respond(503)
    with pytest.raises(SourceError):
        await collect()


@respx.mock
async def test_probe_looks_past_pages_that_are_not_events():
    pages = {f"category/{i}": event_page(markup=False) for i in range(12)} | {f"e{i}": on(f"2026-11-{16 + i}") for i in range(3)}
    serve_site(pages)
    async with httpx.AsyncClient() as client:
        preview, _ = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("e0"), BELGRADE)
    assert [e.day for e in preview.examples] == [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)]


@respx.mock
async def test_probe_shows_coming_events_soonest_first():
    serve_site({"past": on("2026-11-10", name="Прошло"), "late": on("2026-11-25", name="Позже"), "soon": on("2026-11-16", name="Скоро")})
    async with httpx.AsyncClient() as client:
        preview, _ = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("late"), BELGRADE)
    assert [e.title for e in preview.examples] == ["Скоро", "Позже"]


@respx.mock
async def test_page_text_changing_around_the_same_event_is_not_read_again(reading):
    container, source, collect, now = reading
    routes = serve_site({"soon": event_page(name="Скоро", startDate="2026-11-18T19:00:00.000Z", description="Коротко.", text="Новое: статья 1")})
    await collect()
    for post in container.posts.unprocessed([source.id]):
        container.posts.mark_processed(post.id, ReadingRules.POSTS)
    routes["soon"].respond(200, text=event_page(name="Скоро", startDate="2026-11-18T19:00:00.000Z", description="Коротко.", text="Новое: статья 2"))
    now[0] = NOW + timedelta(days=1)
    await collect()
    assert routes["soon"].call_count == 2
    assert container.posts.unprocessed([source.id]) == []


@respx.mock
async def test_probe_keeps_only_sitemaps_with_the_section():
    respx.get(page_url("a")).respond(200, text=on("2026-11-16"))
    respx.get("https://site.test/robots.txt").respond(200, text="Sitemap: https://site.test/pages.xml\nSitemap: https://site.test/events.xml\n")
    respx.get("https://site.test/pages.xml").respond(200, text=sitemap(["https://site.test/about"]))
    respx.get("https://site.test/events.xml").respond(200, text=sitemap([page_url("a")]))
    async with httpx.AsyncClient() as client:
        _, site = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)
    assert site.sitemap_urls == ["https://site.test/events.xml"]


@respx.mock
async def test_probe_refuses_a_section_too_big_to_read():
    respx.get(page_url("a")).respond(200, text=on("2026-11-16"))
    respx.get("https://site.test/robots.txt").respond(200, text="Sitemap: https://site.test/sitemap.xml\n")
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap([page_url(str(i)) for i in range(WebSiteProbe.MAX_PAGES + 1)]))
    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceError, match="слишком много"):
            await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe(page_url("a"), BELGRADE)


@respx.mock
async def test_www_and_bare_host_are_one_site():
    respx.get("https://www.site.test/ru/events/a").respond(200, text=on("2026-11-16"))
    respx.get("https://www.site.test/robots.txt").respond(200, text="Sitemap: https://site.test/sitemap.xml\n")
    respx.get("https://site.test/sitemap.xml").respond(200, text=sitemap([page_url("a")]))
    respx.get(page_url("a")).respond(200, text=on("2026-11-16"))
    async with httpx.AsyncClient() as client:
        preview, _ = await WebSiteProbe(client, SitemapReader(client), clock=lambda: NOW).probe("https://www.site.test/ru/events/a", BELGRADE)
    assert preview.handle == "site.test/ru/events/"


@respx.mock
async def test_page_that_was_not_an_event_is_looked_at_again_a_week_later(reading):
    container, source, collect, now = reading
    routes = serve_site({"draft": event_page(markup=False)})
    await collect()
    routes["draft"].respond(200, text=on("2026-11-30", name="Опубликовали"))
    now[0] = NOW + timedelta(days=3)
    assert await collect() == []
    now[0] = NOW + timedelta(days=8)
    assert [p.text.splitlines()[0] for p in await collect()] == ["Опубликовали"]
    assert routes["draft"].call_count == 2


def in_town(town: str) -> dict:
    return {"@type": "Place", "name": "Клуб", "address": {"addressLocality": town}}


@respx.mock
async def test_events_elsewhere_and_online_never_reach_claude(reading):
    container, source, collect, _ = reading
    serve_site({
        "here": on("2026-11-20", name="Здесь", location=in_town("Belgrade")),
        "here_cyrillic": on("2026-11-20", name="Здесь кириллицей", location=in_town("Београд")),
        "novi_sad": on("2026-11-20", name="Нови-Сад", location=in_town("Novi Sad")),
        "online": on("2026-11-20", name="Онлайн", eventAttendanceMode="https://schema.org/OnlineEventAttendanceMode"),
        "nowhere": on("2026-11-20", name="Без города", location=None),
    })
    titles = sorted(p.text.splitlines()[0] for p in await collect())
    assert titles == ["Без города", "Здесь", "Здесь кириллицей"]


@respx.mock
async def test_a_town_is_asked_about_once(reading):
    container, source, collect, now = reading
    serve_site({"a": on("2026-11-20", name="А", location=in_town("Novi Sad")), "b": on("2026-11-21", name="Б", location=in_town("Novi Sad"))})
    await collect()
    now[0] = NOW + timedelta(days=1)
    await collect()
    assert len(collect.judge.calls) == 1


@respx.mock
async def test_when_claude_cannot_tell_the_town_the_event_is_kept(reading):
    container, source, collect, _ = reading
    collect.judge._answer = lambda *_: (_ for _ in ()).throw(LlmError("нет связи"))
    serve_site({"a": on("2026-11-20", name="А", location=in_town("Novi Sad"))})
    assert [p.text.splitlines()[0] for p in await collect()] == ["А"]


def test_pages_stored_by_1_10_0_open_with_the_new_columns(tmp_path):
    from where_to_go.db import Database

    Database(tmp_path / "db.sqlite3").close()
    import sqlite3

    with sqlite3.connect(tmp_path / "db.sqlite3") as raw:
        for column in ("online", "locality"):
            raw.execute(f"ALTER TABLE web_pages DROP COLUMN {column}")
    Database(tmp_path / "db.sqlite3").close()


@respx.mock
async def test_a_site_that_asks_to_slow_down_is_waited_for():
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    route = respx.get(page_url("a")).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(429), httpx.Response(200, text="ok")])
    async with httpx.AsyncClient() as client:
        assert await PageFetcher(client, sleep=sleep).html(page_url("a")) == "ok"
    assert route.call_count == 3
    assert waits[:2] == [3.0, PageFetcher.FIRST_WAIT * 2]


@respx.mock
async def test_a_site_that_keeps_refusing_is_given_up_on_for_now():
    async def sleep(_: float) -> None:
        pass

    respx.get(page_url("a")).respond(429)
    async with httpx.AsyncClient() as client:
        assert await PageFetcher(client, sleep=sleep).html(page_url("a")) is None


@respx.mock
async def test_coming_event_is_rechecked_at_most_once_a_day(reading):
    container, source, collect, now = reading
    routes = serve_site({"soon": on("2026-11-18", name="Скоро")})
    await collect()
    now[0] = NOW + timedelta(hours=5)
    await collect()
    assert routes["soon"].call_count == 1
    now[0] = NOW + timedelta(hours=25)
    await collect()
    assert routes["soon"].call_count == 2


@respx.mock
async def test_page_keeps_the_event_facts_apart_from_the_text(reading):
    container, source, collect, _ = reading
    serve_site({"a": on("2026-11-20", name="А", location={"name": "Клуб", "address": {"streetAddress": "Улица, 1", "addressLocality": "Belgrade"}}, offers={"price": 1500, "priceCurrency": "RSD"})})
    await collect()
    facts = container.web.page_facts(next(iter(container.web.pages(source.id).values())).id)
    assert (facts.start_date, facts.start_time, facts.venue, facts.address, facts.price, facts.currency) == (
        date(2026, 11, 20), time(19, 0), "Клуб", "Улица, 1, Belgrade", 1500.0, "RSD"
    )
