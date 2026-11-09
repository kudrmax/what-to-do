from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from where_to_go.domain import City, Post, Source
from where_to_go.extraction import ExtractionContext, PostExtractor
from where_to_go.images import ImageStore
from where_to_go.linking import EventLinker
from where_to_go.llm import LlmError
from where_to_go.repositories import (
    CityRepository,
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


@dataclass
class RefreshProgress:
    stage: Stage = Stage.IDLE
    started_at: datetime | None = None
    finished_at: datetime | None = None
    new_posts: int = 0
    posts_to_read: int = 0
    posts_read: int = 0
    events_touched: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.stage in (Stage.COLLECTING, Stage.READING, Stage.MERGING)


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
        places: PlaceRepository,
        tags: TagRepository,
        reader: TelegramChannelReader,
        images: ImageStore,
        extractor: PostExtractor,
        linker: EventLinker,
    ) -> None:
        self._settings = settings
        self._cities = cities
        self._sources = sources
        self._posts = posts
        self._mentions = mentions
        self._places = places
        self._tags = tags
        self._reader = reader
        self._images = images
        self._extractor = extractor
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
        city_id = self._settings.active_city_id()
        city = self._cities.get(city_id) if city_id else None
        if city is None:
            raise RuntimeError("не выбран активный город")
        sources = self._sources.in_city(city.id)

        self.progress.stage = Stage.COLLECTING
        await self._bounded(self.COLLECT_CONCURRENCY, [self._collect(s) for s in sources])

        self.progress.stage = Stage.READING
        posts = self._posts.unprocessed([s.id for s in sources])
        self.progress.posts_to_read = len(posts)
        context = self._context(city)
        by_id = {s.id: s for s in sources}
        await self._bounded(
            self.READ_CONCURRENCY, [self._read(batch, by_id, context) for batch in self._extractor.batches(posts)]
        )

        self.progress.stage = Stage.MERGING
        source_ids = set(by_id)
        pending = [m for m in self._mentions.unassigned() if m.source_id in source_ids]
        try:
            self.progress.events_touched = len(await self._linker.link(city.id, pending))
        except LlmError as error:
            self.progress.errors.append(f"Не получилось склеить события: {error}")
        self._sources.recount_events()

    async def _collect(self, source: Source) -> None:
        try:
            found = await self._reader.new_posts(source.handle, source.last_post_id, self._settings.first_read_posts())
        except SourceError as error:
            self._sources.record_error(source.id, str(error))
            self.progress.errors.append(f"{source.title}: {error}")
            return
        for post in found:
            paths = [p for p in [await self._images.save(u) for u in post.image_urls] if p]
            if self._posts.add_new(source.id, post, paths):
                self.progress.new_posts += 1
        self._sources.record_success(source.id, found[-1].external_id if found else None)

    async def _read(self, batch: list[Post], sources: dict[int, Source], context: ExtractionContext) -> None:
        try:
            results = await self._extractor.extract(batch, sources, context)
        except LlmError as error:
            for post in batch:
                self._posts.mark_failed(post.id, str(error))
            self.progress.errors.append(f"Claude не разобрал {len(batch)} постов: {error}")
            return
        for result in results:
            for index, event in enumerate(result.events):
                self._mentions.add(result.post_id, index, event)
            for place in result.places:
                self._places.add(context.city.id, result.post_id, place)
            self._posts.mark_processed(result.post_id)
        self.progress.posts_read += len(batch)

    def _context(self, city: City) -> ExtractionContext:
        tags = self._tags.all()
        fallback = next((t.name for t in tags if t.is_fallback), TagRepository.FALLBACK)
        return ExtractionContext(
            city=city,
            language=self._settings.description_language(),
            tags=[t.name for t in tags if not t.is_fallback],
            fallback_tag=fallback,
        )

    @staticmethod
    async def _bounded(limit: int, jobs: list) -> None:
        semaphore = asyncio.Semaphore(limit)

        async def guarded(job):
            async with semaphore:
                await job

        await asyncio.gather(*(guarded(j) for j in jobs))
