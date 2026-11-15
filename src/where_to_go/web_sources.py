"""A website as a source: found from one link to its event, read from its sitemap at every refresh."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx

from where_to_go.models import CollectedPost, Public, Source, SourceKind, WebPage, WebSite
from where_to_go.repositories import PostRepository, WebRepository
from where_to_go.telegram import SourceError
from where_to_go.web import EventClock, EventMarkup, PageMeta, PageText, SiteAddress, SitemapReader, WebEvent, WebEventText, in_horizon


log = logging.getLogger(__name__)


class SiteExample(Public):
    title: str
    day: date
    time: str | None = None
    url: str


class SitePreview(Public):
    """What adding a link would add: shown to the user before they confirm."""

    kind: SourceKind
    title: str
    handle: str
    pages_found: int = 0
    examples: list[SiteExample] = []


class Section:
    """The pages of a site's section, whichever www and scheme the sitemap writes them with."""

    def __init__(self, prefix: str) -> None:
        parts = urlsplit(prefix)
        self._host = self._bare(parts.netloc)
        self._path = parts.path

    def __contains__(self, url: str) -> bool:
        parts = urlsplit(url)
        return self._bare(parts.netloc) == self._host and parts.path.startswith(self._path) and parts.path != self._path

    @staticmethod
    def _bare(host: str) -> str:
        return host.lower().removeprefix("www.")


class PageFetcher:
    CONCURRENCY = 4

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._limit = asyncio.Semaphore(self.CONCURRENCY)

    async def html(self, url: str) -> str | None:
        """None when the page cannot be had now; it is asked for again at the next refresh."""
        async with self._limit:
            try:
                response = await self._client.get(url, follow_redirects=True)
            except httpx.HTTPError as error:
                log.warning("page %s not downloaded: %s", url, error.__class__.__name__)
                return None
        if response.status_code != 200:
            log.warning("page %s answered %s", url, response.status_code)
            return None
        return response.text

    async def many(self, urls: list[str]) -> dict[str, str | None]:
        pages = await asyncio.gather(*(self.html(u) for u in urls))
        return dict(zip(urls, pages, strict=True))


class WebSiteProbe:
    EXAMPLES = 3
    LOOK_AT = 8
    LOOK_AT_MOST = 80
    TIME_VOTES = 2
    HORIZON_DAYS = 30

    def __init__(self, client: httpx.AsyncClient, sitemaps: SitemapReader, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._fetcher = PageFetcher(client)
        self._sitemaps = sitemaps
        self._clock = clock

    async def probe(self, link: str, zone: ZoneInfo) -> tuple[SitePreview, WebSite]:
        site, path = SiteAddress.parse(link)
        own = await self._fetcher.html(link.strip() if "://" in link else f"https://{link.strip()}")
        if own is None:
            raise SourceError("Сайт не отвечает")
        event = EventMarkup.read(own)
        if event is None:
            raise SourceError("На странице нет разметки события")
        sitemap_url = await self._sitemaps.locate(site)
        section = Section(site + path)
        urls = [u for u in await self._sitemaps.urls(sitemap_url) if u in section]
        if not urls:
            raise SourceError("В списке страниц сайта нет других страниц этого раздела")
        examples = await self._examples(urls, self._clock().astimezone(zone).date())
        votes = [EventClock.detect(event, PageText.main(own), zone)]
        votes += [EventClock.detect(e, PageText.main(html), zone) for _, e, html in examples[: self.TIME_VOTES]]
        clock = EventClock(EventClock.decide(votes), zone)
        host = urlsplit(site).netloc
        preview = SitePreview(
            kind=SourceKind.WEB,
            title=PageMeta.site_name(own) or host,
            handle=host + path,
            pages_found=len(urls),
            examples=[self._example(u, e, clock) for u, e, _ in examples],
        )
        return preview, WebSite(source_id=0, sitemap_url=sitemap_url, prefix=site + path, times_are_local=clock.is_local)

    async def _examples(self, urls: list[str], today: date) -> list[tuple[str, WebEvent, str]]:
        """A few coming events of the section, soonest first; past events and pages that are not events are skipped."""
        found: list[tuple[str, WebEvent, str]] = []
        for start in range(0, min(len(urls), self.LOOK_AT_MOST), self.LOOK_AT):
            looked = await self._fetcher.many(urls[start : start + self.LOOK_AT])
            events = [(u, e, html) for u, html in looked.items() if html and (e := EventMarkup.read(html))]
            found += [(u, e, html) for u, e, html in events if in_horizon(e.start, e.end, today, self.HORIZON_DAYS)]
            if len(found) >= self.EXAMPLES:
                break
        found.sort(key=lambda item: _day(item[1].start))
        return found[: self.EXAMPLES]

    @staticmethod
    def _example(url: str, event: WebEvent, clock: EventClock) -> SiteExample:
        start = clock.local(event.start)
        if isinstance(start, datetime):
            return SiteExample(title=event.name, day=start.date(), time=start.strftime("%H:%M"), url=url)
        return SiteExample(title=event.name, day=start, url=url)


class WebSiteReader:
    """Every refresh: new pages of the sitemap are downloaded once, the coming week is checked again,
    and events within the horizon become posts."""

    RECHECK_DAYS = 7

    def __init__(
        self,
        client: httpx.AsyncClient,
        sitemaps: SitemapReader,
        web: WebRepository,
        posts: PostRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._fetcher = PageFetcher(client)
        self._sitemaps = sitemaps
        self._web = web
        self._posts = posts
        self._clock = clock

    async def collect(self, source: Source, zone: ZoneInfo) -> list[CollectedPost]:
        site = self._web.site(source.id)
        section = Section(site.prefix)
        urls = [u for u in await self._sitemaps.urls(site.sitemap_url) if u in section]
        now = self._clock()
        today = now.astimezone(zone).date()
        known = self._web.pages(source.id)
        due = [u for u in urls if u not in known or self._coming(known[u], today)]
        clock = EventClock(site.times_are_local, zone)
        for url, html in (await self._fetcher.many(due)).items():
            if html is not None:
                known[url] = self._remember(source.id, url, html, known.get(url), clock, now)
        have_posts = self._posts.known_ids(source.id)
        return [
            CollectedPost(external_id=p.id, url=p.url, published_at=p.found_at, text=p.facts, image_urls=[p.image_url] if p.image_url else [])
            for p in known.values()
            if p.is_event and p.id not in have_posts and in_horizon(p.start_day, p.end_day, today, site.horizon_days)
        ]

    def _coming(self, page: WebPage, today: date) -> bool:
        return page.is_event and in_horizon(page.start_day, page.end_day, today, self.RECHECK_DAYS)

    def _remember(self, source_id: int, url: str, html: str, page: WebPage | None, clock: EventClock, now: datetime) -> WebPage:
        page = page or WebPage(source_id=source_id, url=url, is_event=False, found_at=now, checked_at=now)
        event = EventMarkup.read(html)
        page.checked_at = now
        if event is None:
            page.is_event = False
            return self._web.save_page(page)
        facts = WebEventText.render(event, clock, PageText.main(html))
        fingerprint = hashlib.sha1(WebEventText.render(event, clock, "").encode()).hexdigest()
        changed = page.fingerprint is not None and page.fingerprint != fingerprint
        page.is_event = True
        page.start_day = _day(clock.local(event.start))
        page.end_day = _day(clock.local(event.end)) if event.end else None
        page.facts = facts
        page.fingerprint = fingerprint
        page.image_url = event.image
        page = self._web.save_page(page)
        post_id = self._posts.id_of(source_id, page.id) if changed else None
        if post_id is not None:
            self._posts.replace_text(post_id, facts)
        return page


def _day(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value

