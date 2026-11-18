"""Reads public Instagram profiles as an anonymous visitor: no login, no cookies, one request at a time."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import httpx

from where_to_go.instagram import Highlight, InstagramPage, PostSummary, ProfileSummary
from where_to_go.models import CollectedPost, InstagramReading, InstagramUrls
from where_to_go.telegram import SourceError

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}

NOT_FOUND = 404


class InstagramRefused(SourceError):
    """status is None when Instagram didn't answer at all; collected keeps what was read before the refusal."""

    def __init__(self, status: int | None = None, collected: list[CollectedPost] | None = None) -> None:
        super().__init__("Instagram refused to show the profile. It will be tried again on the next refresh.")
        self.status = status
        self.collected = collected or []


class InstagramRequests:
    """Every Instagram page of a refresh goes through here, so all sources share one pause between requests."""

    EXCERPT = 2048

    def __init__(
        self,
        client: httpx.AsyncClient,
        pause: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._pause = pause
        self._sleep = sleep
        self._clock = clock
        self._lock = asyncio.Lock()
        self._last_end: float | None = None

    async def page(self, url: str, has_data: Callable[[InstagramPage], bool]) -> InstagramPage:
        """The page when it answers 200 with the data asked for; InstagramRefused otherwise."""
        async with self._lock:
            await self._wait_for_turn()
            try:
                response = await self._get(url)
            finally:
                self._last_end = self._clock()
        if response.status_code == NOT_FOUND:
            log.info("Instagram has no page %s", url)
            raise InstagramRefused(NOT_FOUND)
        page = InstagramPage(response.text) if response.status_code == 200 else None
        if page is None or not has_data(page):
            log.warning(
                "Instagram refused %s: %s %s %s", url, response.status_code, dict(response.headers), response.text[: self.EXCERPT]
            )
            raise InstagramRefused(response.status_code)
        return page

    async def _wait_for_turn(self) -> None:
        if self._last_end is not None:
            wait = self._last_end + self._pause - self._clock()
            if wait > 0:
                await self._sleep(wait)

    async def _get(self, url: str) -> httpx.Response:
        self._client.cookies.clear()
        try:
            return await self._client.get(url, headers=HEADERS, follow_redirects=False)
        except httpx.HTTPError as error:
            log.warning("Instagram didn't answer %s: %r", url, error)
            raise InstagramRefused from error
        finally:
            self._client.cookies.clear()


class InstagramReader:
    """The first refusal ends the source's reading for this refresh: no more requests, no retries."""

    STORIES_READ_WITHIN = timedelta(days=30)

    def __init__(self, requests: InstagramRequests) -> None:
        self._requests = requests

    async def title(self, name: str) -> tuple[str, int]:
        try:
            profile = await self._profile(name)
        except InstagramRefused as refused:
            if refused.status is None:
                raise SourceError("Instagram didn't respond") from refused
            raise SourceError("Instagram refused to show the profile. Try again later.") from refused
        return profile.title or name, len(profile.highlights)

    async def collect(self, name: str, known: set[int], reading: InstagramReading, now: datetime) -> list[CollectedPost]:
        """Posts and stories not stored yet, oldest first."""
        found: dict[int, CollectedPost] = {}
        try:
            profile = await self._profile(name)
            if reading.posts:
                for summary in profile.posts:
                    post = await self._post(summary) if summary.pk not in known else None
                    if post is not None:
                        found[post.external_id] = post
            if reading.stories:
                await self._stories(profile.highlights, known, now, found)
        except InstagramRefused as refused:
            raise InstagramRefused(refused.status, self._oldest_first(found)) from refused
        return self._oldest_first(found)

    @staticmethod
    def _oldest_first(found: dict[int, CollectedPost]) -> list[CollectedPost]:
        return sorted(found.values(), key=lambda post: post.published_at)

    async def _profile(self, name: str) -> ProfileSummary:
        try:
            page = await self._requests.page(InstagramUrls.profile(name), lambda p: p.profile() is not None or p.private())
        except InstagramRefused as refused:
            if refused.status == NOT_FOUND:
                raise SourceError("This Instagram profile doesn't exist") from refused
            raise
        profile = None if page.private() else page.profile()
        if profile is None:
            raise SourceError("This Instagram profile is private")
        return profile

    async def _post(self, summary: PostSummary) -> CollectedPost | None:
        """None when the post was deleted after the profile listed it."""
        page = await self._unless_gone(InstagramUrls.post(summary.code), lambda p: p.post() is not None)
        details = page.post() if page is not None else None
        if details is None:
            return None
        place = f"\n\nPlace: {details.place}" if details.place else ""
        return CollectedPost(
            external_id=details.pk,
            url=InstagramUrls.post(details.code),
            published_at=details.published_at,
            text=details.caption + place,
            image_urls=details.image_urls,
            video_urls=details.video_urls,
            video_covers=details.video_covers,
        )

    async def _unless_gone(self, url: str, has_data: Callable[[InstagramPage], bool]) -> InstagramPage | None:
        try:
            return await self._requests.page(url, has_data)
        except InstagramRefused as refused:
            if refused.status == NOT_FOUND:
                return None
            raise

    async def _stories(self, highlights: list[Highlight], known: set[int], now: datetime, found: dict[int, CollectedPost]) -> None:
        """A story pinned to several highlights is one story, told under the first highlight it was found in."""
        for highlight in highlights:
            page = await self._unless_gone(InstagramUrls.highlight(highlight.id), lambda p: p.holds_highlight(highlight.id))
            for story in page.stories() if page is not None else []:
                if story.pk in known or story.pk in found:
                    continue
                found[story.pk] = CollectedPost(
                    external_id=story.pk,
                    url=InstagramUrls.highlight(highlight.id),
                    published_at=story.published_at,
                    text=f"Pinned story from the highlight «{highlight.title}»",
                    image_urls=[story.image_url] if story.image_url else [],
                    video_urls=[story.video_url] if story.video_url else [],
                    video_covers={story.video_url: story.image_url} if story.video_url and story.image_url else {},
                    read=now - story.published_at <= self.STORIES_READ_WITHIN,
                )
