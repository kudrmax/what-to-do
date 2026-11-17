"""Reads public Instagram profiles as an anonymous visitor: no login, no cookies, one request at a time."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import httpx

from where_to_go.instagram import Highlight, InstagramPage, PostDetails, PostSummary, ProfileSummary
from where_to_go.models import CollectedPost, InstagramReading, InstagramUrls
from where_to_go.telegram import SourceError

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "Upgrade-Insecure-Requests": "1",
}


class InstagramRefused(SourceError):
    def __init__(self, status: int | None = None) -> None:
        super().__init__("Instagram refused to show the profile; will try again on the next refresh")
        self.status = status


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
        self._last_start: float | None = None

    async def page(self, url: str) -> InstagramPage:
        async with self._lock:
            await self._wait_for_turn()
            response = await self._get(url)
        if response.status_code != 200:
            log.warning(
                "Instagram refused %s: %s %s %s", url, response.status_code, dict(response.headers), response.text[: self.EXCERPT]
            )
            raise InstagramRefused(response.status_code)
        return InstagramPage(response.text)

    async def _wait_for_turn(self) -> None:
        if self._last_start is not None:
            wait = self._last_start + self._pause - self._clock()
            if wait > 0:
                await self._sleep(wait)
        self._last_start = self._clock()

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
    STORIES_READ_WITHIN = timedelta(days=30)

    def __init__(self, requests: InstagramRequests) -> None:
        self._requests = requests

    async def title(self, name: str) -> tuple[str, int]:
        profile = await self._profile(name)
        return profile.title or name, len(profile.highlights)

    async def collect(self, name: str, known: set[int], reading: InstagramReading, now: datetime) -> list[CollectedPost]:
        """Posts and stories not stored yet, oldest first."""
        profile = await self._profile(name)
        found: list[CollectedPost] = []
        if reading.posts:
            found += [await self._post(summary, now) for summary in profile.posts if summary.pk not in known]
        if reading.stories:
            found += await self._stories(profile.highlights, known, now)
        return sorted(found, key=lambda post: post.published_at)

    async def _profile(self, name: str) -> ProfileSummary:
        url = InstagramUrls.profile(name)
        try:
            page = await self._requests.page(url)
        except InstagramRefused as refused:
            if refused.status == 404:
                raise SourceError("This Instagram profile doesn't exist") from refused
            raise
        profile = page.profile()
        if profile is not None:
            return profile
        if page.private():
            raise SourceError("This Instagram profile is private")
        log.warning("Instagram refused %s: the page came without the profile: %s", url, page.excerpt())
        raise InstagramRefused(200)

    async def _post(self, summary: PostSummary, now: datetime) -> CollectedPost:
        try:
            details = (await self._requests.page(InstagramUrls.post(summary.code))).post()
        except InstagramRefused:
            details = None
        return self._from_details(details) if details is not None else self._from_summary(summary, now)

    @staticmethod
    def _from_details(details: PostDetails) -> CollectedPost:
        place = f"\n\nPlace: {details.place}" if details.place else ""
        return CollectedPost(
            external_id=details.pk,
            url=InstagramUrls.post(details.code),
            published_at=details.published_at,
            text=details.caption + place,
            image_urls=details.image_urls,
            video_urls=details.video_urls,
        )

    @staticmethod
    def _from_summary(summary: PostSummary, now: datetime) -> CollectedPost:
        """The profile knows the post's day but not its time."""
        day = summary.day
        return CollectedPost(
            external_id=summary.pk,
            url=InstagramUrls.post(summary.code),
            published_at=datetime(day.year, day.month, day.day, 12, tzinfo=UTC) if day else now,
            text=summary.caption,
            image_urls=[summary.image_url] if summary.image_url else [],
        )

    async def _stories(self, highlights: list[Highlight], known: set[int], now: datetime) -> list[CollectedPost]:
        """A story pinned to several highlights is one story, told under the first highlight it was found in."""
        found: dict[int, CollectedPost] = {}
        for highlight in highlights:
            for story in (await self._requests.page(InstagramUrls.highlight(highlight.id))).stories():
                if story.pk in known or story.pk in found:
                    continue
                found[story.pk] = CollectedPost(
                    external_id=story.pk,
                    url=InstagramUrls.highlight(highlight.id),
                    published_at=story.published_at,
                    text=f"Pinned story from the highlight «{highlight.title}»",
                    image_urls=[story.image_url] if story.image_url else [],
                    video_urls=[story.video_url] if story.video_url else [],
                    read=now - story.published_at <= self.STORIES_READ_WITHIN,
                )
        return list(found.values())
