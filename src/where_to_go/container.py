from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from where_to_go.db import Database
from where_to_go.extraction import PostExtractor
from where_to_go.feed import Feed
from where_to_go.images import ImageStore
from where_to_go.linking import EventCards, EventLinker
from where_to_go.llm import ClaudeJsonLlm, JsonLlm
from where_to_go.matching import CandidateFinder, DuplicateJudge
from where_to_go.refresh import RefreshService
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
from where_to_go.resolution import EventResolver
from where_to_go.telegram import TelegramChannelReader

PROVISIONAL_TAGS = [
    "Концерт",
    "Вечеринка",
    "Лекция",
    "Стендап",
    "Театр",
    "Кино",
    "Выставка",
    "Игры и квизы",
    "Мастер-класс",
    "Встреча",
    "Спорт",
    "Прогулка",
    "Маркет",
    "Детям",
]

EXTRACTION_MODEL = "claude-haiku-5-5"
MATCHING_MODEL = "claude-haiku-5-5"


@dataclass
class Container:
    db: Database
    http: httpx.AsyncClient
    settings: SettingsRepository
    cities: CityRepository
    sources: SourceRepository
    posts: PostRepository
    mentions: MentionRepository
    places: PlaceRepository
    tags: TagRepository
    events: EventRepository
    images: ImageStore
    reader: TelegramChannelReader
    cards: EventCards
    feed: Feed
    refresh: RefreshService

    @classmethod
    def build(
        cls,
        data_dir: Path,
        extraction_llm: JsonLlm | None = None,
        matching_llm: JsonLlm | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> Container:
        db = Database(data_dir / "where-to-go.sqlite3")
        http = http or httpx.AsyncClient(timeout=30, headers={"User-Agent": "where-to-go/0.1"})
        settings = SettingsRepository(db)
        cities = CityRepository(db)
        sources = SourceRepository(db)
        posts = PostRepository(db)
        mentions = MentionRepository(db)
        places = PlaceRepository(db)
        tags = TagRepository(db)
        tags.ensure_seeded(PROVISIONAL_TAGS)
        events = EventRepository(db)
        images = ImageStore(data_dir / "images", http)
        reader = TelegramChannelReader(http)
        cards = EventCards(events, mentions, EventResolver(TagRepository.FALLBACK))
        linker = EventLinker(
            CandidateFinder(events), DuplicateJudge(matching_llm or ClaudeJsonLlm(MATCHING_MODEL)), cards
        )
        refresh = RefreshService(
            settings=settings,
            cities=cities,
            sources=sources,
            posts=posts,
            mentions=mentions,
            places=places,
            tags=tags,
            reader=reader,
            images=images,
            extractor=PostExtractor(extraction_llm or ClaudeJsonLlm(EXTRACTION_MODEL)),
            linker=linker,
        )
        return cls(
            db=db,
            http=http,
            settings=settings,
            cities=cities,
            sources=sources,
            posts=posts,
            mentions=mentions,
            places=places,
            tags=tags,
            events=events,
            images=images,
            reader=reader,
            cards=cards,
            feed=Feed(events),
            refresh=refresh,
        )

    async def close(self) -> None:
        await self.http.aclose()
        self.db.close()
