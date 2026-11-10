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
from where_to_go.originals import OriginalPosts
from where_to_go.photos import PhotoTranscriber
from where_to_go.refresh import PostReader, RefreshService
from where_to_go.releases import PROJECT_DIR, Releases, ReleaseSource
from where_to_go.repositories import (
    CityRepository,
    DevNoteRepository,
    EventRepository,
    MentionRepository,
    PhotoTextRepository,
    PlaceRepository,
    PostRepository,
    PotentialSourceRepository,
    SettingsRepository,
    SourceRepository,
    TagRepository,
)
from where_to_go.resolution import EventResolver
from where_to_go.sources import PotentialSources, SourceCatalog
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


@dataclass
class Container:
    db: Database
    http: httpx.AsyncClient
    settings: SettingsRepository
    cities: CityRepository
    sources: SourceRepository
    catalog: SourceCatalog
    potential_sources: PotentialSources
    posts: PostRepository
    mentions: MentionRepository
    places: PlaceRepository
    tags: TagRepository
    events: EventRepository
    dev_notes: DevNoteRepository
    images: ImageStore
    photos: PhotoTranscriber
    originals: OriginalPosts
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
        photo_llm: JsonLlm | None = None,
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
        cards = EventCards(events, mentions, EventResolver(tags.fallback), db.transaction)
        matching_llm = matching_llm or ClaudeJsonLlm(lambda: settings.load().matching_model)
        extraction_llm = extraction_llm or ClaudeJsonLlm(lambda: settings.load().extraction_model)
        photo_llm = photo_llm or ClaudeJsonLlm(lambda: settings.load().photo_model)
        linker = EventLinker(CandidateFinder(events), DuplicateJudge(matching_llm, lambda: settings.load().matching_prompt), cards)
        photo_texts = PhotoTextRepository(db)
        catalog = SourceCatalog(sources, events, cards, reader)
        potential_sources = PotentialSources(PotentialSourceRepository(db), sources, catalog)
        photos = PhotoTranscriber(photo_llm, images, photo_texts, lambda: settings.load().photo_prompt)
        post_mentions = PostMentions(mentions, cards)
        post_reader = PostReader(
            settings=settings,
            tags=tags,
            posts=posts,
            post_mentions=post_mentions,
            places=places,
            potential_sources=potential_sources,
            extractor=PostExtractor(extraction_llm),
            photos=photos,
            photo_texts=photo_texts,
            atomically=db.transaction,
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
            photos=photos,
            post_reader=post_reader,
            post_mentions=post_mentions,
            linker=linker,
        )
        return cls(
            db=db,
            http=http,
            settings=settings,
            cities=cities,
            sources=sources,
            catalog=catalog,
            potential_sources=potential_sources,
            posts=posts,
            mentions=mentions,
            places=places,
            tags=tags,
            events=events,
            dev_notes=DevNoteRepository(db),
            images=images,
            photos=photos,
            originals=OriginalPosts(photo_texts),
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
