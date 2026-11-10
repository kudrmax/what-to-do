from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx

from where_to_go.about import USER_AGENT
from where_to_go.db import Database
from where_to_go.extraction import PostExtractor
from where_to_go.feed import Feed
from where_to_go.images import ImageStore
from where_to_go.linking import EventCards, EventLinker, PostMentions
from where_to_go.llm import ClaudeJsonLlm, JsonLlm
from where_to_go.matching import CandidateFinder, DuplicateJudge
from where_to_go.refresh import PostReader, RefreshService
from where_to_go.releases import PROJECT_DIR, Releases, ReleaseSource
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
from where_to_go.sources import SourceCatalog
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
FALLBACK_TAG = "не распознано"

EXTRACTION_MODEL = "claude-sonnet-5-5"
MATCHING_MODEL = "claude-haiku-5-5"


@dataclass
class Container:
    db: Database
    http: httpx.AsyncClient
    settings: SettingsRepository
    cities: CityRepository
    sources: SourceRepository
    catalog: SourceCatalog
    posts: PostRepository
    mentions: MentionRepository
    places: PlaceRepository
    tags: TagRepository
    events: EventRepository
    images: ImageStore
    cards: EventCards
    linker: EventLinker
    feed: Feed
    post_reader: PostReader
    refresh: RefreshService
    releases: Releases

    @classmethod
    def build(
        cls,
        data_dir: Path,
        extraction_llm: JsonLlm | None = None,
        matching_llm: JsonLlm | None = None,
        http: httpx.AsyncClient | None = None,
        project_dir: Path = PROJECT_DIR,
        release_source: ReleaseSource | None = None,
    ) -> Container:
        db = Database(data_dir / "where-to-go.sqlite3")
        http = http or httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT})
        settings = SettingsRepository(db)
        cities = CityRepository(db, settings)
        sources = SourceRepository(db)
        posts = PostRepository(db)
        mentions = MentionRepository(db)
        places = PlaceRepository(db)
        tags = TagRepository(db)
        tags.ensure_seeded(PROVISIONAL_TAGS, FALLBACK_TAG)
        events = EventRepository(db)
        images = ImageStore(data_dir / "images", http)
        reader = TelegramChannelReader(http)
        cards = EventCards(events, mentions, EventResolver(tags.fallback))
        linker = EventLinker(CandidateFinder(events), DuplicateJudge(matching_llm or ClaudeJsonLlm(MATCHING_MODEL), lambda: settings.load().matching_prompt), cards)
        post_reader = PostReader(
            settings=settings,
            tags=tags,
            posts=posts,
            post_mentions=PostMentions(mentions, cards),
            places=places,
            extractor=PostExtractor(extraction_llm or ClaudeJsonLlm(EXTRACTION_MODEL), images),
        )
        refresh = RefreshService(
            settings=settings,
            cities=cities,
            sources=sources,
            posts=posts,
            mentions=mentions,
            events=events,
            reader=reader,
            images=images,
            post_reader=post_reader,
            linker=linker,
        )
        return cls(
            db=db,
            http=http,
            settings=settings,
            cities=cities,
            sources=sources,
            catalog=SourceCatalog(sources, events, cards, reader),
            posts=posts,
            mentions=mentions,
            places=places,
            tags=tags,
            events=events,
            images=images,
            cards=cards,
            linker=linker,
            feed=Feed(events),
            post_reader=post_reader,
            refresh=refresh,
            releases=Releases.build(project_dir, data_dir, release_source),
        )

    async def close(self) -> None:
        await self.http.aclose()
        self.db.close()
