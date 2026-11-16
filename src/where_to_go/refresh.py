from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from enum import StrEnum

import anyio
from pydantic import computed_field
from sqlmodel import Field, SQLModel

from where_to_go.models import City, ExtractedEvent, Post, Public, Source, SourceKind
from where_to_go.extraction import ExtractionContext, PostExtractor
from where_to_go.images import ImageStore
from where_to_go.linking import Atomically, EventLinker, PostMentions
from where_to_go.llm import ClaudeSignedOutError, LlmError
from where_to_go.photos import PhotoTranscriber
from where_to_go.sources import PotentialSources
from where_to_go.repositories import (
    CityRepository,
    EventRepository,
    MentionRepository,
    PlaceRepository,
    PhotoTextRepository,
    PostRepository,
    SettingsRepository,
    SourceRepository,
    TagRepository,
    WebRepository,
)
from where_to_go.source_types import SourceTypes
from where_to_go.telegram import SourceError

log = logging.getLogger(__name__)


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


class Stage(StrEnum):
    IDLE = "idle"
    COLLECTING = "collecting"
    PHOTOS = "photos"
    READING = "reading"
    MERGING = "merging"
    DONE = "done"
    FAILED = "failed"

    @property
    def is_running(self) -> bool:
        return self in (Stage.COLLECTING, Stage.PHOTOS, Stage.READING, Stage.MERGING)


class RefreshProgress(Public):
    stage: Stage = Stage.IDLE
    started_at: datetime | None = None
    stage_started_at: datetime | None = Field(default=None, description="When the current stage began: how fast it goes tells how long is left")
    finished_at: datetime | None = None
    sources_to_collect: int = 0
    sources_collected: int = Field(default=0, description="Sources read, with or without an error")
    pages_to_fetch: int = Field(default=0, description="Website pages to download in this refresh; known only as each site's list is read")
    pages_fetched: int = 0
    announcements_to_merge: int = Field(default=0, description="Announcements of this refresh to place on cards")
    announcements_merged: int = 0
    new_posts: int = Field(default=0, description="Posts downloaded in this refresh")
    photos_to_read: int = Field(default=0, description="Photos Claude transcribes in this refresh")
    photos_read: int = 0
    posts_to_read: int = Field(default=0, description="Posts Claude reads in this refresh")
    posts_read: int = 0
    events_touched: int = Field(default=0, description="Cards created or updated")
    errors: list[str] = Field(default_factory=list, description="Human-readable, ready to show")
    claude_signed_out: bool = Field(default=False, description="Claude Code has no login: nothing was read; the user must sign in first")

    @computed_field
    @property
    def running(self) -> bool:
        return self.stage.is_running

    def enter(self, stage: Stage) -> None:
        self.stage = stage
        self.stage_started_at = datetime.now(UTC)

    def planned(self, pages: int) -> None:
        self.pages_to_fetch += pages

    def fetched(self) -> None:
        self.pages_fetched += 1

    def claude_failed(self, error: LlmError, message: str) -> None:
        """One line per failure, except a missing login: it fails every call alike and is said once."""
        if not isinstance(error, ClaudeSignedOutError):
            self.errors.append(message)
        elif not self.claude_signed_out:
            self.claude_signed_out = True
            self.errors.append(str(error))


class PostReader:
    """Turns stored posts into mentions and places with Claude; the one way posts get read."""

    def __init__(
        self,
        *,
        settings: SettingsRepository,
        tags: TagRepository,
        posts: PostRepository,
        post_mentions: PostMentions,
        places: PlaceRepository,
        potential_sources: PotentialSources,
        extractor: PostExtractor,
        photos: PhotoTranscriber,
        photo_texts: PhotoTextRepository,
        web: WebRepository,
        atomically: Atomically,
    ) -> None:
        self._atomically = atomically
        self._web = web
        self._photos = photos
        self._photo_texts = photo_texts
        self._settings = settings
        self._tags = tags
        self._posts = posts
        self._post_mentions = post_mentions
        self._places = places
        self._potential_sources = potential_sources
        self._extractor = extractor

    def batches(self, posts: list[Post]) -> list[list[Post]]:
        return self._extractor.batches(posts, self._photo_texts.of(name for post in posts for name in PhotoTranscriber.shown(post)))

    def context(self, city: City) -> ExtractionContext:
        tags = self._tags.all()
        settings = self._settings.load()
        return ExtractionContext(
            city=city,
            prompt=settings.extraction_prompt,
            language=settings.description_language,
            tags=[t.name for t in tags if not t.is_fallback],
            fallback_tag=self._tags.fallback(),
            priority_wish=settings.priority_wish,
        )

    async def read(self, batch: list[Post], sources: dict[int, Source], context: ExtractionContext) -> None:
        """Reads a batch; on a Claude failure the posts stay unread and are retried next time."""
        try:
            texts = self._photo_texts.of(name for post in batch for name in PhotoTranscriber.shown(post))
            results = await self._extractor.extract(batch, sources, context, texts)
        except LlmError as error:
            for post in batch:
                self._posts.mark_failed(post.id, str(error))
            raise
        by_id = {post.id: post for post in batch}
        for result in results:
            post = by_id[result.post_id]
            events = self._settled(post, sources[post.source_id], result.events)
            with self._atomically():
                self._post_mentions.store(result.post_id, events)
                self._places.forget_post(result.post_id)
                for place in result.places:
                    self._places.add(context.city.id, result.post_id, place)
                self._potential_sources.note(context.city.id, by_id[result.post_id], result.channels)
                self._posts.mark_processed(result.post_id, context.rules)


    def _settled(self, post: Post, source: Source, events: list[tuple[ExtractedEvent, int | None]]) -> list[tuple[ExtractedEvent, int | None]]:
        """An event page's own facts replace Claude's reading of them; a page Claude split into several events is left as read."""
        if source.kind != SourceKind.WEB or len(events) != 1:
            return events
        facts = self._web.page_facts(post.external_id)
        if facts is None:
            return events
        [(event, photo)] = events
        return [(facts.settle(event), photo)]


class RefreshService:
    COLLECT_CONCURRENCY = 4
    PHOTO_CONCURRENCY = 3
    READ_CONCURRENCY = 3

    def __init__(
        self,
        *,
        settings: SettingsRepository,
        cities: CityRepository,
        sources: SourceRepository,
        posts: PostRepository,
        mentions: MentionRepository,
        events: EventRepository,
        types: SourceTypes,
        images: ImageStore,
        photos: PhotoTranscriber,
        post_reader: PostReader,
        post_mentions: PostMentions,
        linker: EventLinker,
    ) -> None:
        self._post_mentions = post_mentions
        self._photos = photos
        self._settings = settings
        self._cities = cities
        self._sources = sources
        self._posts = posts
        self._mentions = mentions
        self._events = events
        self._types = types
        self._images = images
        self._post_reader = post_reader
        self._linker = linker
        self.progress = RefreshProgress()
        self._task: asyncio.Task | None = None
        self._cancel: anyio.CancelScope | None = None

    def start(self) -> RefreshProgress:
        if not self.progress.running:
            self.progress = RefreshProgress(stage=Stage.COLLECTING, started_at=datetime.now(UTC), stage_started_at=datetime.now(UTC))
            self._cancel = anyio.CancelScope()
            self._task = asyncio.create_task(self._run_safely(self._cancel))
        return self.progress

    async def wait(self) -> RefreshProgress:
        if self._task is not None:
            await self._task
        return self.progress

    async def stop(self) -> None:
        """Cancels a refresh in progress and waits until Claude's processes are gone;
        posts already read stay saved, the rest are read next time.

        An anyio cancel, not task.cancel(): the Claude SDK finishes stopping its process only then."""
        if self._task is None or self._cancel is None or self._task.done():
            return
        self._cancel.cancel()
        await asyncio.wait({self._task})

    async def _run_safely(self, cancel: anyio.CancelScope) -> None:
        try:
            with cancel:
                await self.run()
                self.progress.stage = Stage.DONE
            if cancel.cancelled_caught:
                self.progress.errors.append("Refresh stopped: the app was closed")
                self.progress.stage = Stage.FAILED
        except Exception as error:
            log.exception("refresh failed")
            self.progress.errors.append(f"Refresh stopped: {error}")
            self.progress.stage = Stage.FAILED
        finally:
            self.progress.finished_at = datetime.now(UTC)

    async def run(self) -> None:
        city = self._cities.active()
        if city is None:
            raise RuntimeError("no active city selected")
        sources = {s.id: s for s in self._sources.in_city(city.id) if not s.paused}

        self.progress.enter(Stage.COLLECTING)
        self.progress.sources_to_collect = len(sources)
        await self._bounded(self.COLLECT_CONCURRENCY, [self._collect(s, city) for s in sources.values()])

        context = self._post_reader.context(city)
        posts = self._posts.to_read(sources, context.rules, self._settings.load().recent_posts)

        self.progress.enter(Stage.PHOTOS)
        with_photos = [p for p in posts if sources[p.source_id].kind != SourceKind.WEB]  # a site gives its facts as text
        photos = self._photos.untranscribed(with_photos)
        self.progress.photos_to_read = len(photos)
        await self._bounded(self.PHOTO_CONCURRENCY, [self._transcribe(batch) for batch in self._photos.batches(photos)])
        unreadable = set(self._photos.untranscribed(with_photos))
        posts = [p for p in posts if unreadable.isdisjoint(PhotoTranscriber.shown(p))]

        self.progress.enter(Stage.READING)
        self.progress.posts_to_read = len(posts)
        await self._bounded(self.READ_CONCURRENCY, [self._read(batch, sources, context) for batch in self._post_reader.batches(posts)])

        self._post_mentions.share_posters()

        self.progress.enter(Stage.MERGING)
        try:
            unassigned = self._mentions.unassigned(sources)
            self.progress.announcements_to_merge = len(unassigned)
            self.progress.events_touched = len(await self._linker.link(city.id, unassigned, self._merged))
        except LlmError as error:
            self.progress.claude_failed(error, f"Couldn't merge events: {error}")
        self._sources.recount_events(self._events)

    def _merged(self, count: int) -> None:
        self.progress.announcements_merged += count

    async def _collect(self, source: Source, city: City) -> None:
        try:
            await self._collect_one(source, city)
        finally:
            self.progress.sources_collected += 1

    async def _collect_one(self, source: Source, city: City) -> None:
        try:
            found = await self._types.of(source.kind).collect(source, city, self.progress)
        except SourceError as error:
            self._sources.record_error(source.id, str(error))
            self.progress.errors.append(f"{source.title}: {error}")
            return
        except Exception as error:  # one broken source must not stop the others
            log.exception("collecting %s failed", source.title)
            message = f"couldn't read it: {error.__class__.__name__}"
            self._sources.record_error(source.id, message)
            self.progress.errors.append(f"{source.title}: {message}")
            return
        for post in found:
            paths = [p for p in [await self._images.save(u) for u in post.image_urls] if p]
            if self._posts.add_new(source.id, post, paths):
                self.progress.new_posts += 1
        self._sources.record_success(source.id)

    async def _transcribe(self, batch: list[str]) -> None:
        """A post waits for its photos: read without them it would lose what its poster says."""
        try:
            await self._photos.transcribe(batch)
        except LlmError as error:
            self.progress.claude_failed(error, f"Claude couldn't read {_count(len(batch), 'photo')}; their posts will be read next time: {error}")
            return
        self.progress.photos_read += len(batch)

    async def _read(self, batch: list[Post], sources: dict[int, Source], context: ExtractionContext) -> None:
        try:
            await self._post_reader.read(batch, sources, context)
        except LlmError as error:
            self.progress.claude_failed(error, f"Claude couldn't read some of the new posts and pages ({len(batch)}): {error}")
            return
        self.progress.posts_read += len(batch)

    @staticmethod
    async def _bounded(limit: int, jobs: list) -> None:
        """An anyio task group, not asyncio.gather: gather would pass a stop to Claude's calls as task.cancel(),
        which cuts short the SDK's stopping of its process and leaves it running."""
        limiter = anyio.CapacityLimiter(limit)

        async def guarded(job):
            try:
                async with limiter:
                    await job
            finally:
                job.close()  # a job stopped before its turn never ran

        try:
            async with anyio.create_task_group() as group:
                for job in jobs:
                    group.start_soon(guarded, job)
        except BaseExceptionGroup as failed:
            raise failed.exceptions[0] from None
