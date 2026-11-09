from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import computed_field
from sqlmodel import Field, SQLModel

from where_to_go.models import City, Post, Source
from where_to_go.extraction import ExtractionContext, PostExtractor
from where_to_go.images import ImageStore
from where_to_go.linking import EventLinker
from where_to_go.llm import LlmError
from where_to_go.repositories import (
    CityRepository,
    EventRepository,
    MentionRepository,
    PlaceRepository,
    PostRepository,
    SettingsRepository,
    SourceRepository,
    TagRepository,
)
from where_to_go.telegram import SourceError, TelegramChannelReader

log = logging.getLogger(__name__)


class Stage(StrEnum):
    IDLE = "idle"
    COLLECTING = "collecting"
    READING = "reading"
    MERGING = "merging"
    DONE = "done"
    FAILED = "failed"

    @property
    def is_running(self) -> bool:
        return self in (Stage.COLLECTING, Stage.READING, Stage.MERGING)


class RefreshProgress(SQLModel):
    stage: Stage = Stage.IDLE
    started_at: datetime | None = None
    finished_at: datetime | None = None
    new_posts: int = Field(default=0, description="Posts downloaded in this refresh")
    posts_to_read: int = Field(default=0, description="Posts Claude reads in this refresh")
    posts_read: int = 0
    events_touched: int = Field(default=0, description="Cards created or updated")
    errors: list[str] = Field(default_factory=list, description="Human-readable, ready to show")

    @computed_field
    @property
    def running(self) -> bool:
        return self.stage.is_running


class PostReader:
    """Turns stored posts into mentions and places with Claude; the one way posts get read."""

    def __init__(
        self,
        *,
        settings: SettingsRepository,
        tags: TagRepository,
        posts: PostRepository,
        mentions: MentionRepository,
        places: PlaceRepository,
        extractor: PostExtractor,
    ) -> None:
        self._settings = settings
        self._tags = tags
        self._posts = posts
        self._mentions = mentions
        self._places = places
        self._extractor = extractor

    def batches(self, posts: list[Post]) -> list[list[Post]]:
        return self._extractor.batches(posts)

    def context(self, city: City) -> ExtractionContext:
        tags = self._tags.all()
        settings = self._settings.load()
        return ExtractionContext(
            city=city,
            prompt=settings.extraction_prompt,
            language=settings.description_language,
            tags=[t.name for t in tags if not t.is_fallback],
            fallback_tag=self._tags.fallback(),
        )

    async def read(self, batch: list[Post], sources: dict[int, Source], context: ExtractionContext) -> None:
        """Reads a batch; on a Claude failure the posts stay unread and are retried next time."""
        try:
            results = await self._extractor.extract(batch, sources, context)
        except LlmError as error:
            for post in batch:
                self._posts.mark_failed(post.id, str(error))
            raise
        for result in results:
            for index, (event, image) in enumerate(result.events):
                self._mentions.add(result.post_id, index, event, image)
            for place in result.places:
                self._places.add(context.city.id, result.post_id, place)
            self._posts.mark_processed(result.post_id)


class RefreshService:
    COLLECT_CONCURRENCY = 4
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
        reader: TelegramChannelReader,
        images: ImageStore,
        post_reader: PostReader,
        linker: EventLinker,
    ) -> None:
        self._settings = settings
        self._cities = cities
        self._sources = sources
        self._posts = posts
        self._mentions = mentions
        self._events = events
        self._reader = reader
        self._images = images
        self._post_reader = post_reader
        self._linker = linker
        self.progress = RefreshProgress()
        self._task: asyncio.Task | None = None

    def start(self) -> RefreshProgress:
        if not self.progress.running:
            self.progress = RefreshProgress(stage=Stage.COLLECTING, started_at=datetime.now(UTC))
            self._task = asyncio.create_task(self._run_safely())
        return self.progress

    async def wait(self) -> RefreshProgress:
        if self._task is not None:
            await self._task
        return self.progress

    async def _run_safely(self) -> None:
        try:
            await self.run()
            self.progress.stage = Stage.DONE
        except Exception as error:
            log.exception("refresh failed")
            self.progress.errors.append(f"Обновление прервалось: {error}")
            self.progress.stage = Stage.FAILED
        finally:
            self.progress.finished_at = datetime.now(UTC)

    async def run(self) -> None:
        city = self._cities.active()
        if city is None:
            raise RuntimeError("не выбран активный город")
        sources = {s.id: s for s in self._sources.in_city(city.id)}

        self.progress.stage = Stage.COLLECTING
        await self._bounded(self.COLLECT_CONCURRENCY, [self._collect(s) for s in sources.values()])

        self.progress.stage = Stage.READING
        posts = self._posts.unprocessed(sources)
        self.progress.posts_to_read = len(posts)
        context = self._post_reader.context(city)
        await self._bounded(self.READ_CONCURRENCY, [self._read(batch, sources, context) for batch in self._post_reader.batches(posts)])

        self.progress.stage = Stage.MERGING
        try:
            self.progress.events_touched = len(await self._linker.link(city.id, self._mentions.unassigned(sources)))
        except LlmError as error:
            self.progress.errors.append(f"Не получилось склеить события: {error}")
        self._sources.recount_events(self._events)

    async def _collect(self, source: Source) -> None:
        try:
            found = await self._reader.new_posts(source.handle, self._posts.known_ids(source.id), self._settings.load().recent_posts)
        except SourceError as error:
            self._sources.record_error(source.id, str(error))
            self.progress.errors.append(f"{source.title}: {error}")
            return
        for post in found:
            paths = [p for p in [await self._images.save(u) for u in post.image_urls] if p]
            if self._posts.add_new(source.id, post, paths):
                self.progress.new_posts += 1
        self._sources.record_success(source.id)

    async def _read(self, batch: list[Post], sources: dict[int, Source], context: ExtractionContext) -> None:
        try:
            await self._post_reader.read(batch, sources, context)
        except LlmError as error:
            self.progress.errors.append(f"Claude не разобрал {len(batch)} постов: {error}")
            return
        self.progress.posts_read += len(batch)

    @staticmethod
    async def _bounded(limit: int, jobs: list) -> None:
        semaphore = asyncio.Semaphore(limit)

        async def guarded(job):
            async with semaphore:
                await job

        await asyncio.gather(*(guarded(j) for j in jobs))
