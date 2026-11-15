"""The kinds of sources — Telegram channels and websites — behind one interface: the catalog adds them,
the refresh reads them, and neither knows which kind it holds."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from zoneinfo import ZoneInfo

from where_to_go.models import City, CollectedPost, Source, SourceKind, WebSite
from where_to_go.repositories import PostRepository, SettingsRepository, WebRepository
from where_to_go.telegram import SourceLink, TelegramChannelReader, TelegramHandle
from where_to_go.web_sources import NO_TALLY, PageTally, SitePreview, WebSiteProbe, WebSiteReader


class SourceType(ABC):
    kind: ClassVar[SourceKind]
    already_added: ClassVar[str]

    @abstractmethod
    def accepts(self, link: str) -> bool: ...

    def handle_of(self, link: str) -> str | None:
        """The source's handle when the link alone tells it, so a duplicate is caught before any request."""
        return None

    @abstractmethod
    async def preview(self, city: City, link: str, title: str | None = None) -> SitePreview:
        """What the link would add; SourceError when it cannot be a source. A given title is not looked up."""

    async def attach(self, source: Source, city: City, link: str) -> None:
        """Keeps what this kind needs besides the source itself."""

    @abstractmethod
    async def collect(self, source: Source, city: City, tally: PageTally = NO_TALLY) -> list[CollectedPost]:
        """Posts not stored yet; pages downloaded on the way are counted in the tally."""


class TelegramSourceType(SourceType):
    kind = SourceKind.TELEGRAM
    already_added = "This channel is already added"

    def __init__(self, reader: TelegramChannelReader, posts: PostRepository, settings: SettingsRepository) -> None:
        self._reader = reader
        self._posts = posts
        self._settings = settings

    def accepts(self, link: str) -> bool:
        return SourceLink.is_telegram(link)

    def handle_of(self, link: str) -> str | None:
        return TelegramHandle.parse(link)

    async def preview(self, city: City, link: str, title: str | None = None) -> SitePreview:
        handle = TelegramHandle.parse(link)
        return SitePreview(kind=self.kind, title=title or await self._reader.title(handle), handle=handle)

    async def collect(self, source: Source, city: City, tally: PageTally = NO_TALLY) -> list[CollectedPost]:
        return await self._reader.new_posts(source.handle, self._posts.known_ids(source.id), self._settings.load().recent_posts)


class WebSourceType(SourceType):
    """A site is probed once for its preview; adding it soon after keeps what the preview found."""

    kind = SourceKind.WEB
    already_added = "This site is already added"
    PREVIEW_KEPT = timedelta(minutes=10)

    def __init__(
        self,
        probe: WebSiteProbe,
        reader: WebSiteReader,
        web: WebRepository,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._probe = probe
        self._reader = reader
        self._web = web
        self._clock = clock
        self._probed: dict[tuple[int, str], tuple[datetime, SitePreview, WebSite]] = {}

    def accepts(self, link: str) -> bool:
        return not SourceLink.is_telegram(link)

    async def preview(self, city: City, link: str, title: str | None = None) -> SitePreview:
        preview, _ = await self._probed_site(city, link)
        return preview.model_copy(update={"title": title}) if title else preview

    async def attach(self, source: Source, city: City, link: str) -> None:
        _, site = await self._probed_site(city, link)
        self._web.add_site(WebSite(**{**site.model_dump(), "source_id": source.id}))
        self._probed.pop(self._key(city, link), None)

    async def collect(self, source: Source, city: City, tally: PageTally = NO_TALLY) -> list[CollectedPost]:
        return await self._reader.collect(source, city, tally)

    async def _probed_site(self, city: City, link: str) -> tuple[SitePreview, WebSite]:
        key = self._key(city, link)
        now = self._clock()
        kept = self._probed.get(key)
        if kept is not None and now - kept[0] < self.PREVIEW_KEPT:
            return kept[1], kept[2]
        preview, site = await self._probe.probe(link, ZoneInfo(city.timezone))
        self._probed[key] = (now, preview, site)
        return preview, site

    @staticmethod
    def _key(city: City, link: str) -> tuple[int, str]:
        return city.id, link.strip()


class SourceTypes:
    def __init__(self, *types: SourceType) -> None:
        self._types = types

    def for_link(self, link: str) -> SourceType:
        return next(t for t in self._types if t.accepts(link))

    def of(self, kind: SourceKind) -> SourceType:
        return next(t for t in self._types if t.kind == kind)
