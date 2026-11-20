from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from where_to_go.about import USER_AGENT
from where_to_go.cities import CityCatalog
from where_to_go.db import Database
from where_to_go.extraction import PostExtractor
from where_to_go.feed import Feed
from where_to_go.frames import VideoFrames
from where_to_go.images import ImageStore
from where_to_go.linking import DetailsLinks, EventCards, EventLinker, PostMentions
from where_to_go.linked_posts import LinkedPosts
from where_to_go.llm import ClaudeJsonLlm, JsonLlm
from where_to_go.matching import CandidateFinder, DuplicateJudge
from where_to_go.originals import OriginalPosts
from where_to_go.phone_page.cipher import SnapshotCipher
from where_to_go.phone_page.config import PhonePageConfigRepository
from where_to_go.phone_page.github import GitHubPagesPublisher
from where_to_go.phone_page.service import PagesPublisher, PhonePageService
from where_to_go.phone_page.snapshot import SnapshotBuilder
from where_to_go.photos import PhotoTranscriber
from where_to_go.refresh import PostReader, RefreshService
from where_to_go.retagging import EventRetagger, RetagService
from where_to_go.claude_login import ClaudeSignInFlow
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.releases import Releases, ReleaseSource
from where_to_go.repositories import (
    CityRepository,
    CollectionRepository,
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
    InstagramRepository,
    WebRepository,
)
from where_to_go.resolution import EventResolver
from where_to_go.sources import PotentialSources, SourceCatalog
from where_to_go.statistics import Statistics
from where_to_go.telegram import TelegramChannelReader
from where_to_go.web import SitemapReader
from where_to_go.localities import LocalityJudge, LocalityRepository
from where_to_go.instagram_reader import InstagramReader, InstagramRequests
from where_to_go.source_types import InstagramSourceType, SourceTypes, TelegramSourceType, WebSourceType
from where_to_go.web_sources import WebSiteProbe, WebSiteReader



@dataclass
class Container:
    db: Database
    http: httpx.AsyncClient
    instagram_http: httpx.AsyncClient
    settings: SettingsRepository
    cities: CityRepository
    city_catalog: CityCatalog
    sources: SourceRepository
    web: WebRepository
    instagram: InstagramRepository
    catalog: SourceCatalog
    potential_sources: PotentialSources
    posts: PostRepository
    mentions: MentionRepository
    places: PlaceRepository
    tags: TagRepository
    events: EventRepository
    dev_notes: DevNoteRepository
    collections: CollectionRepository
    images: ImageStore
    photos: PhotoTranscriber
    originals: OriginalPosts
    cards: EventCards
    linker: EventLinker
    feed: Feed
    post_reader: PostReader
    refresh: RefreshService
    retag: RetagService
    releases: Releases
    claude_sign_in: ClaudeSignInFlow
    statistics: Statistics
    phone_config: PhonePageConfigRepository
    phone_page: PhonePageService

    @classmethod
    def build(
        cls,
        data_dir: Path,
        extraction_llm: JsonLlm | None = None,
        matching_llm: JsonLlm | None = None,
        photo_llm: JsonLlm | None = None,
        http: httpx.AsyncClient | None = None,
        project: ProjectPaths | None = None,
        release_source: ReleaseSource | None = None,
        phone_publisher: PagesPublisher | None = None,
        phone_bundle: Path | None = None,
        instagram_pause: float = 1.0,
    ) -> Container:
        project = project or ProjectPaths.here()
        db = Database(data_dir / "where-to-go.sqlite3")
        http = http or httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT})
        instagram_http = httpx.AsyncClient(timeout=30, follow_redirects=False)
        settings = SettingsRepository(db)
        cities = CityRepository(db, settings)
        sources = SourceRepository(db)
        web = WebRepository(db)
        instagram = InstagramRepository(db)
        posts = PostRepository(db)
        mentions = MentionRepository(db)
        places = PlaceRepository(db)
        tags = TagRepository(db)
        events = EventRepository(db)
        images = ImageStore(data_dir / "images", http)
        frames = VideoFrames(data_dir / "images", http)
        reader = TelegramChannelReader(http)
        cards = EventCards(events, mentions, EventResolver(tags.fallback), db.transaction)
        matching_llm = matching_llm or ClaudeJsonLlm(lambda: settings.load().matching_model)
        extraction_llm = extraction_llm or ClaudeJsonLlm(lambda: settings.load().extraction_model)
        photo_llm = photo_llm or ClaudeJsonLlm(lambda: settings.load().photo_model)
        linker = EventLinker(CandidateFinder(events), DuplicateJudge(matching_llm, lambda: settings.load().matching_prompt), cards, DetailsLinks(mentions, events))
        photo_texts = PhotoTextRepository(db)
        sitemaps = SitemapReader(http)
        types = SourceTypes(
            TelegramSourceType(reader, posts, settings),
            WebSourceType(
                WebSiteProbe(http, sitemaps),
                WebSiteReader(http, sitemaps, web, posts, LocalityJudge(matching_llm, LocalityRepository(db))),
                web,
            ),
            InstagramSourceType(InstagramReader(InstagramRequests(instagram_http, instagram_pause)), posts, instagram),
        )
        catalog = SourceCatalog(sources, events, cards, types)
        potential_sources = PotentialSources(PotentialSourceRepository(db), sources, posts, catalog)
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
            web=web,
            atomically=db.transaction,
        )
        refresh = RefreshService(
            settings=settings,
            cities=cities,
            sources=sources,
            instagram=instagram,
            posts=posts,
            mentions=mentions,
            events=events,
            types=types,
            images=images,
            frames=frames,
            photos=photos,
            post_reader=post_reader,
            post_mentions=post_mentions,
            linker=linker,
            linked_posts=LinkedPosts(posts, reader, images),
        )
        feed = Feed(events, sources)
        originals = OriginalPosts(photo_texts)
        phone_config = PhonePageConfigRepository(db)
        phone_page = PhonePageService(
            config=phone_config,
            builder=SnapshotBuilder(
                settings=settings,
                cities=cities,
                sources=sources,
                tags=tags,
                feed=feed,
                mentions=mentions,
                originals=originals,
                images=images,
            ),
            publisher=phone_publisher or GitHubPagesPublisher(http),
            cipher_factory=SnapshotCipher,
            bundle_dir=phone_bundle or project.dist / "phone",
            clock=lambda: datetime.now(UTC),
        )
        return cls(
            db=db,
            http=http,
            instagram_http=instagram_http,
            settings=settings,
            cities=cities,
            city_catalog=CityCatalog(cities, tags, lambda: refresh.progress.running),
            sources=sources,
            web=web,
            instagram=instagram,
            catalog=catalog,
            potential_sources=potential_sources,
            posts=posts,
            mentions=mentions,
            places=places,
            tags=tags,
            events=events,
            dev_notes=DevNoteRepository(db),
            collections=CollectionRepository(db),
            images=images,
            photos=photos,
            originals=originals,
            cards=cards,
            linker=linker,
            feed=feed,
            post_reader=post_reader,
            refresh=refresh,
            retag=RetagService(EventRetagger(extraction_llm, cities, events, tags)),
            releases=Releases.build(project, data_dir, release_source),
            statistics=Statistics(db),
            claude_sign_in=ClaudeSignInFlow(),
            phone_config=phone_config,
            phone_page=phone_page,
        )

    async def close(self) -> None:
        await self.phone_page.stop()
        await self.refresh.stop()
        await self.retag.stop()
        self.claude_sign_in.stop()
        await self.http.aclose()
        await self.instagram_http.aclose()
        self.db.close()
