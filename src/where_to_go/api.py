from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from pathlib import Path
from typing import Annotated
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from where_to_go.container import Container
from where_to_go.domain import City, Event, EventKind, Mark, Plan, Source, SourceKind
from where_to_go.feed import DEFAULT_HORIZON, FeedFilter
from where_to_go.refresh import RefreshProgress
from where_to_go.repositories import SettingsRepository
from where_to_go.telegram import SourceError, TelegramHandle

# ---------- response and request shapes ----------


class CityOut(BaseModel):
    id: int
    name: str
    timezone: str
    active: bool


class CityIn(BaseModel):
    name: str = Field(min_length=1)
    timezone: str


class SettingsOut(BaseModel):
    active_city_id: int | None
    description_language: str
    first_read_posts: int


class SettingsIn(BaseModel):
    active_city_id: int | None = None
    description_language: str | None = None
    first_read_posts: int | None = Field(default=None, ge=1, le=300)


class SourceOut(BaseModel):
    id: int
    city_id: int
    kind: SourceKind
    title: str
    url: str
    last_refreshed_at: datetime | None
    last_error: str | None
    events_found: int


class SourceIn(BaseModel):
    link: str = Field(min_length=1)
    title: str | None = None


class SourcePatch(BaseModel):
    title: str = Field(min_length=1)


class TagOut(BaseModel):
    id: int
    name: str
    is_fallback: bool


class TagIn(BaseModel):
    name: str = Field(min_length=1)


class ConflictOut(BaseModel):
    field: str
    values: list[str]


class MarkOut(BaseModel):
    interest: int | None
    plan: Plan | None


class MarkIn(BaseModel):
    interest: int | None = Field(default=None, ge=1, le=5)
    plan: Plan | None = None


class EventOut(BaseModel):
    id: int
    kind: EventKind
    title: str
    original_title: str
    description: str
    start_date: date
    end_date: date | None
    start_time: time | None
    recurrence: str | None
    venue: str | None
    address: str | None
    map_url: str | None
    price: str | None
    tags: list[str]
    image_url: str | None
    is_cancelled: bool
    conflicts: list[ConflictOut]
    source_ids: list[int]
    mark: MarkOut


class OccurrenceOut(BaseModel):
    date: date
    event: EventOut


class MentionOut(BaseModel):
    id: int
    source_id: int
    source_title: str
    post_url: str
    published_at: datetime
    original_title: str
    post_text: str
    from_organizer: bool
    update_kind: str


class EventDetailOut(EventOut):
    mentions: list[MentionOut]


class MergeIn(BaseModel):
    other_event_id: int


class SplitIn(BaseModel):
    mention_id: int


class RefreshOut(BaseModel):
    stage: str
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    new_posts: int
    posts_to_read: int
    posts_read: int
    events_touched: int
    errors: list[str]


class PlaceOut(BaseModel):
    id: int
    name: str
    address: str | None
    description: str
    post_url: str


# ---------- mapping ----------


class Presenter:
    def __init__(self, container: Container) -> None:
        self._c = container

    def city(self, city: City) -> CityOut:
        return CityOut(id=city.id, name=city.name, timezone=city.timezone, active=city.id == self._c.settings.active_city_id())

    @staticmethod
    def source(source: Source) -> SourceOut:
        return SourceOut(
            id=source.id,
            city_id=source.city_id,
            kind=source.kind,
            title=source.title,
            url=source.url,
            last_refreshed_at=source.last_refreshed_at,
            last_error=source.last_error,
            events_found=source.events_found,
        )

    @staticmethod
    def event(event: Event) -> EventOut:
        place = event.address or event.venue
        return EventOut(
            id=event.id,
            kind=event.kind,
            title=event.title,
            original_title=event.original_title,
            description=event.description,
            start_date=event.start_date,
            end_date=event.end_date,
            start_time=event.start_time,
            recurrence=event.rrule,
            venue=event.venue,
            address=event.address,
            map_url=f"https://www.google.com/maps/search/?api=1&query={quote_plus(place)}" if place else None,
            price=event.price,
            tags=list(event.tags),
            image_url=f"/images/{event.image_path}" if event.image_path else None,
            is_cancelled=event.is_cancelled,
            conflicts=[ConflictOut(field=c.field, values=list(c.values)) for c in event.conflicts],
            source_ids=list(event.source_ids),
            mark=MarkOut(interest=event.mark.interest, plan=event.mark.plan),
        )

    def event_detail(self, event: Event) -> EventDetailOut:
        mentions = []
        for mention in self._c.mentions.of_event(event.id):
            post = self._c.posts.get(mention.post_id)
            mentions.append(
                MentionOut(
                    id=mention.id,
                    source_id=mention.source_id,
                    source_title=self._c.sources.get(mention.source_id).title,
                    post_url=post.url,
                    published_at=post.published_at,
                    original_title=mention.data.original_title,
                    post_text=post.text,
                    from_organizer=mention.data.from_organizer,
                    update_kind=mention.data.update_kind.value,
                )
            )
        return EventDetailOut(**self.event(event).model_dump(), mentions=mentions)

    @staticmethod
    def refresh(progress: RefreshProgress) -> RefreshOut:
        return RefreshOut(
            stage=progress.stage.value,
            running=progress.running,
            started_at=progress.started_at,
            finished_at=progress.finished_at,
            new_posts=progress.new_posts,
            posts_to_read=progress.posts_to_read,
            posts_read=progress.posts_read,
            events_touched=progress.events_touched,
            errors=list(progress.errors),
        )


# ---------- application ----------


def _container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(_container)]


def create_app(container_factory) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container_factory()
        yield
        await app.state.container.close()

    app = FastAPI(title="Чем заняться", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    def active_city(c: ContainerDepontainer) -> City:
        city_id = c.settings.active_city_id()
        city = c.cities.get(city_id) if city_id else None
        if city is None:
            raise HTTPException(409, "Сначала добавьте город")
        return city

    # settings and cities

    @app.get("/settings", response_model=SettingsOut)
    def get_settings(c: ContainerDep):
        return SettingsOut(
            active_city_id=c.settings.active_city_id(),
            description_language=c.settings.description_language(),
            first_read_posts=c.settings.first_read_posts(),
        )

    @app.patch("/settings", response_model=SettingsOut)
    def patch_settings(body: SettingsIn, c: ContainerDep):
        if body.active_city_id is not None:
            if c.cities.get(body.active_city_id) is None:
                raise HTTPException(404, "Нет такого города")
            c.settings.set(SettingsRepository.ACTIVE_CITY, str(body.active_city_id))
        if body.description_language:
            c.settings.set(SettingsRepository.DESCRIPTION_LANGUAGE, body.description_language)
        if body.first_read_posts is not None:
            c.settings.set(SettingsRepository.FIRST_READ_POSTS, str(body.first_read_posts))
        return get_settings(c)

    @app.get("/cities", response_model=list[CityOut])
    def list_cities(c: ContainerDep):
        present = Presenter(c)
        return [present.city(city) for city in c.cities.all()]

    @app.post("/cities", response_model=CityOut, status_code=201)
    def add_city(body: CityIn, c: ContainerDep):
        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "Неизвестный часовой пояс") from None
        city = c.cities.add(body.name.strip(), body.timezone)
        if c.settings.active_city_id() is None:
            c.settings.set(SettingsRepository.ACTIVE_CITY, str(city.id))
        return Presenter(c).city(city)

    # sources

    @app.get("/sources", response_model=list[SourceOut])
    def list_sources(c: ContainerDep):
        return [Presenter.source(s) for s in c.sources.in_city(active_city(c).id)]

    @app.post("/sources", response_model=SourceOut, status_code=201)
    async def add_source(body: SourceIn, c: ContainerDep):
        city = active_city(c)
        try:
            handle = TelegramHandle.parse(body.link)
            title = (body.title or "").strip() or await c.reader.title(handle)
        except SourceError as error:
            raise HTTPException(422, str(error)) from None
        if any(s.handle.lower() == handle.lower() for s in c.sources.in_city(city.id)):
            raise HTTPException(409, "Этот канал уже добавлен")
        return Presenter.source(c.sources.add(city.id, SourceKind.TELEGRAM, handle, title))

    @app.patch("/sources/{source_id}", response_model=SourceOut)
    def rename_source(source_id: int, body: SourcePatch, c: ContainerDep):
        _source_or_404(c, source_id)
        c.sources.rename(source_id, body.title.strip())
        return Presenter.source(c.sources.get(source_id))

    @app.delete("/sources/{source_id}", status_code=204)
    def delete_source(source_id: int, c: ContainerDep):
        _source_or_404(c, source_id)
        event_ids = {e.id for e in c.events.in_city(c.sources.get(source_id).city_id) if source_id in e.source_ids}
        c.sources.delete(source_id)
        for event_id in event_ids:
            c.cards.refresh(event_id)

    # tags

    @app.get("/tags", response_model=list[TagOut])
    def list_tags(c: ContainerDep):
        return [TagOut(id=t.id, name=t.name, is_fallback=t.is_fallback) for t in c.tags.all()]

    @app.post("/tags", response_model=TagOut, status_code=201)
    def add_tag(body: TagIn, c: ContainerDep):
        tag = c.tags.add(body.name.strip())
        return TagOut(id=tag.id, name=tag.name, is_fallback=False)

    @app.patch("/tags/{tag_id}", response_model=TagOut)
    def rename_tag(tag_id: int, body: TagIn, c: ContainerDep):
        try:
            c.tags.rename(tag_id, body.name.strip())
        except KeyError:
            raise HTTPException(404, "Нет такого тега") from None
        tag = next(t for t in c.tags.all() if t.id == tag_id)
        return TagOut(id=tag.id, name=tag.name, is_fallback=tag.is_fallback)

    # events

    @app.get("/events", response_model=list[OccurrenceOut])
    def feed(
        c: ContainerDep,
        start: date | None = None,
        end: date | None = None,
        tags: Annotated[list[str], Query()] = [],
        sources: Annotated[list[int], Query()] = [],
        plans: Annotated[list[Plan], Query()] = [],
        only_timed: bool = False,
        hide_multiday: bool = False,
        hide_marked: bool = True,
    ):
        city = active_city(c)
        first = start or datetime.now(ZoneInfo(city.timezone)).date()
        criteria = FeedFilter(
            start=first,
            end=end or first + DEFAULT_HORIZON,
            tags=frozenset(tags),
            source_ids=frozenset(sources),
            only_timed=only_timed,
            hide_multiday=hide_multiday,
            hide_marked=hide_marked,
            plans=frozenset(plans),
        )
        return [OccurrenceOut(date=o.date, event=Presenter.event(o.event)) for o in c.feed.occurrences(city.id, criteria)]

    @app.get("/events/{event_id}", response_model=EventDetailOut)
    def event_detail(event_id: int, c: ContainerDep):
        return Presenter(c).event_detail(_event_or_404(c, event_id))

    @app.put("/events/{event_id}/mark", response_model=EventOut)
    def set_mark(event_id: int, body: MarkIn, c: ContainerDep):
        _event_or_404(c, event_id)
        c.events.set_mark(event_id, Mark(body.interest, body.plan))
        return Presenter.event(c.events.get(event_id))

    @app.post("/events/{event_id}/merge", response_model=EventDetailOut)
    def merge(event_id: int, body: MergeIn, c: ContainerDep):
        _event_or_404(c, event_id)
        _event_or_404(c, body.other_event_id)
        try:
            c.cards.merge(event_id, body.other_event_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return Presenter(c).event_detail(c.events.get(event_id))

    @app.post("/events/{event_id}/split", response_model=EventDetailOut)
    def split(event_id: int, body: SplitIn, c: ContainerDep):
        _event_or_404(c, event_id)
        try:
            new_id = c.cards.split(event_id, body.mention_id)
        except KeyError:
            raise HTTPException(404, "У карточки нет такого источника") from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return Presenter(c).event_detail(c.events.get(new_id))

    @app.get("/places", response_model=list[PlaceOut])
    def places(c: ContainerDep):
        return [
            PlaceOut(id=p["id"], name=p["name"], address=p["address"], description=p["description"], post_url=p["post_url"])
            for p in c.places.in_city(active_city(c).id)
        ]

    # refresh and files

    @app.post("/refresh", response_model=RefreshOut, status_code=202)
    async def start_refresh(c: ContainerDep):
        active_city(c)
        return Presenter.refresh(c.refresh.start())

    @app.get("/refresh", response_model=RefreshOut)
    def refresh_status(c: ContainerDep):
        return Presenter.refresh(c.refresh.progress)

    @app.get("/images/{name}")
    def image(name: str, c: ContainerDep):
        path = c.images.path(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path)

    return app


def _source_or_404(c: ContainerDepontainer, source_id: int) -> Source:
    try:
        return c.sources.get(source_id)
    except KeyError:
        raise HTTPException(404, "Нет такого источника") from None


def _event_or_404(c: ContainerDepontainer, event_id: int) -> Event:
    try:
        return c.events.get(event_id)
    except KeyError:
        raise HTTPException(404, "Нет такого события") from None


def default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "where-to-go"
