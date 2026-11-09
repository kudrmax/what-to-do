from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from where_to_go.api.errors import validation_error
from where_to_go.api.presenter import Presenter
from where_to_go.api.schemas import (
    CityIn,
    CityOut,
    EventDetailOut,
    EventOut,
    MarkIn,
    MergeIn,
    OccurrenceOut,
    PlaceOut,
    RefreshOut,
    SourceIn,
    SourceOut,
    SourcePatch,
    SplitIn,
    TagIn,
    TagOut,
)
from where_to_go.container import Container
from where_to_go.domain import City, Event, Mark, Plan, Source, SourceKind
from where_to_go.feed import DEFAULT_HORIZON, FeedFilter
from where_to_go.settings import AppSettings, SettingsChange
from where_to_go.telegram import SourceError, TelegramHandle

DESCRIPTION = """
Local backend of «Чем заняться». It reads public Telegram channels, Claude turns posts into event cards
and merges the same event announced by several channels into one card.

**First run.** The app starts empty: add a city (`POST /cities`, the first one becomes active),
add channels (`POST /sources`), press refresh (`POST /refresh`) and poll `GET /refresh` until `running` is false.

**Active city.** Sources, the feed, places and refresh work with the active city only.
Without a city these answer 409.

**Errors** come as `{"detail": "<text in Russian, ready to show>"}`.
"""

TAGS = [
    {"name": "settings", "description": "Settings and cities"},
    {"name": "sources", "description": "Telegram channels of the active city"},
    {"name": "tags", "description": "The fixed list of tags Claude may put on cards"},
    {"name": "events", "description": "The feed, a card, marks, manual merge and split"},
    {"name": "refresh", "description": "Collect new posts and turn them into cards"},
]

ContainerFactory = Callable[[], Container]


def _container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(_container)]


def _active_city(c: ContainerDep) -> City:
    city_id = c.settings.load().active_city_id
    city = c.cities.get(city_id) if city_id else None
    if city is None:
        raise HTTPException(409, "Сначала добавьте город")
    return city


CityDep = Annotated[City, Depends(_active_city)]


def _source(source_id: int, c: ContainerDep) -> Source:
    try:
        return c.sources.get(source_id)
    except KeyError:
        raise HTTPException(404, "Нет такого источника") from None


def _event(event_id: int, c: ContainerDep) -> Event:
    try:
        return c.events.get(event_id)
    except KeyError:
        raise HTTPException(404, "Нет такого события") from None


SourceDep = Annotated[Source, Depends(_source)]
EventDep = Annotated[Event, Depends(_event)]


def create_app(container_factory: ContainerFactory) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container_factory()
        yield
        await app.state.container.close()

    app = FastAPI(title="Чем заняться", version="0.1.0", description=DESCRIPTION, openapi_tags=TAGS, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_exception_handler(RequestValidationError, validation_error)

    # ---------- settings and cities ----------

    @app.get("/settings", response_model=AppSettings, tags=["settings"])
    def get_settings(c: ContainerDep):
        """All settings of the app."""
        return c.settings.load()

    @app.patch("/settings", response_model=AppSettings, tags=["settings"])
    def patch_settings(body: SettingsChange, c: ContainerDep):
        """Changes the settings that are sent. Switching the active city switches the feed and the sources."""
        change = body.model_dump(exclude_unset=True, exclude_none=True)
        if "active_city_id" in change and c.cities.get(change["active_city_id"]) is None:
            raise HTTPException(404, "Нет такого города")
        return c.settings.update(**change)

    @app.get("/cities", response_model=list[CityOut], tags=["settings"])
    def list_cities(c: ContainerDep):
        """Every city the user has added; old ones stay after a move."""
        present = Presenter(c)
        return [present.city(city) for city in c.cities.all()]

    @app.post("/cities", response_model=CityOut, status_code=201, tags=["settings"])
    def add_city(body: CityIn, c: ContainerDep):
        """Adds a city. The first city becomes active; later ones are activated with `PATCH /settings`."""
        try:
            ZoneInfo(body.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise HTTPException(422, "Неизвестный часовой пояс") from None
        city = c.cities.add(body.name.strip(), body.timezone)
        if c.settings.load().active_city_id is None:
            c.settings.update(active_city_id=city.id)
        return Presenter(c).city(city)

    # ---------- sources ----------

    @app.get("/sources", response_model=list[SourceOut], tags=["sources"])
    def list_sources(c: ContainerDep, city: CityDep):
        """Channels of the active city with the result of their last refresh."""
        return [Presenter.source(s) for s in c.sources.in_city(city.id)]

    @app.post("/sources", response_model=SourceOut, status_code=201, tags=["sources"])
    async def add_source(body: SourceIn, c: ContainerDep, city: CityDep):
        """Adds a public Telegram channel to the active city. Its posts are read on the next refresh.

        422: not a channel link, or the channel is closed or has no web preview. 409: already added.
        """
        try:
            handle = TelegramHandle.parse(body.link)
            title = (body.title or "").strip() or await c.reader.title(handle)
        except SourceError as error:
            raise HTTPException(422, str(error)) from None
        if any(s.handle.lower() == handle.lower() for s in c.sources.in_city(city.id)):
            raise HTTPException(409, "Этот канал уже добавлен")
        return Presenter.source(c.sources.add(city.id, SourceKind.TELEGRAM, handle, title))

    @app.patch("/sources/{source_id}", response_model=SourceOut, tags=["sources"])
    def rename_source(body: SourcePatch, c: ContainerDep, source: SourceDep):
        """Renames a source."""
        c.sources.rename(source.id, body.title.strip())
        return Presenter.source(c.sources.get(source.id))

    @app.delete("/sources/{source_id}", status_code=204, tags=["sources"])
    def delete_source(c: ContainerDep, source: SourceDep):
        """Deletes a source with its posts. Cards only it announced disappear; shared cards lose its post."""
        event_ids = {e.id for e in c.events.in_city(source.city_id) if source.id in e.source_ids}
        c.sources.delete(source.id)
        for event_id in event_ids:
            c.cards.refresh(event_id)

    # ---------- tags ----------

    @app.get("/tags", response_model=list[TagOut], tags=["tags"])
    def list_tags(c: ContainerDep):
        """Tags in display order; the fallback «не распознано» is always last."""
        return [Presenter.tag(t) for t in c.tags.all()]

    @app.post("/tags", response_model=TagOut, status_code=201, tags=["tags"])
    def add_tag(body: TagIn, c: ContainerDep):
        """Adds a tag. Claude uses it for posts read from now on."""
        return Presenter.tag(c.tags.add(body.name.strip()))

    @app.patch("/tags/{tag_id}", response_model=TagOut, tags=["tags"])
    def rename_tag(tag_id: int, body: TagIn, c: ContainerDep):
        """Renames a tag everywhere, on existing cards too."""
        try:
            c.tags.rename(tag_id, body.name.strip())
        except KeyError:
            raise HTTPException(404, "Нет такого тега") from None
        return Presenter.tag(next(t for t in c.tags.all() if t.id == tag_id))

    # ---------- events ----------

    @app.get("/events", response_model=list[OccurrenceOut], tags=["events"])
    def feed(
        c: ContainerDep,
        city: CityDep,
        start: Annotated[date | None, Query(description="First day; default: today in the city's time zone")] = None,
        end: Annotated[date | None, Query(description="Last day, inclusive; default: start + 14 days")] = None,
        tags: Annotated[list[str], Query(description="Any of these tags; repeat the parameter for several")] = [],
        sources: Annotated[list[int], Query(description="Cards that have a post from any of these sources")] = [],
        plans: Annotated[list[Plan], Query(description="Only these plans, e.g. maybe and sure for «Собираюсь пойти»")] = [],
        only_timed: Annotated[bool, Query(description="Only events with a known date and time")] = False,
        hide_multiday: Annotated[bool, Query(description="Hide exhibitions, festivals and other multiday events")] = False,
        hide_marked: Annotated[
            bool,
            Query(description="Hide cards whose plan is no or went; interest does not matter"),
        ] = True,
    ):
        """The feed: cards laid out on days, sorted by day, then time; unknown time and multiday events go last in a day."""
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

    @app.get("/events/{event_id}", response_model=EventDetailOut, tags=["events"])
    def event_detail(c: ContainerDep, event: EventDep):
        """An open card with the original posts it is built from."""
        return Presenter(c).event_detail(event)

    @app.put("/events/{event_id}/mark", response_model=EventOut, tags=["events"])
    def set_mark(body: MarkIn, c: ContainerDep, event: EventDep):
        """Sets interest and plan of a card. Both fields are written as sent."""
        c.events.set_mark(event.id, Mark(body.interest, body.plan))
        return Presenter.event(c.events.get(event.id))

    @app.post("/events/{event_id}/merge", response_model=EventDetailOut, tags=["events"])
    def merge(body: MergeIn, c: ContainerDep, event: EventDep):
        """The user says two cards are one event: `other_event_id` joins this card and is deleted.
        Claude never undoes a manual merge."""
        _event(body.other_event_id, c)
        try:
            c.cards.merge(event.id, body.other_event_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return Presenter(c).event_detail(c.events.get(event.id))

    @app.post("/events/{event_id}/split", response_model=EventDetailOut, tags=["events"])
    def split(body: SplitIn, c: ContainerDep, event: EventDep):
        """Moves one source's post out into a card of its own and returns the new card.
        Claude never undoes a manual split. 422: the card has a single source."""
        try:
            new_id = c.cards.split(event.id, body.mention_id)
        except KeyError:
            raise HTTPException(404, "У карточки нет такого источника") from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return Presenter(c).event_detail(c.events.get(new_id))

    @app.get("/places", response_model=list[PlaceOut], tags=["events"])
    def places(c: ContainerDep, city: CityDep):
        """Places without a date found in posts; they do not appear in the feed."""
        return [
            PlaceOut(id=p["id"], name=p["name"], address=p["address"], description=p["description"], post_url=p["post_url"])
            for p in c.places.in_city(city.id)
        ]

    @app.get("/images/{name}", tags=["events"], response_class=FileResponse)
    def image(name: str, c: ContainerDep):
        """A card image; `image_url` of a card points here."""
        path = c.images.path(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path)

    # ---------- refresh ----------

    @app.post("/refresh", response_model=RefreshOut, status_code=202, tags=["refresh"])
    async def start_refresh(c: ContainerDep, city: CityDep):
        """Starts a refresh of the active city's sources in the background and returns at once.
        A second call while one runs returns the running one."""
        return Presenter.refresh(c.refresh.start())

    @app.get("/refresh", response_model=RefreshOut, tags=["refresh"])
    def refresh_status(c: ContainerDep):
        """Progress of the current or the last refresh; poll it while `running` is true."""
        return Presenter.refresh(c.refresh.progress)

    return app


def default_data_dir() -> Path:
    return Path.home() / "Library" / "Application Support" / "where-to-go"
