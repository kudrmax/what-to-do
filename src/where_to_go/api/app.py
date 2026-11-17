from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ValidationError
from sqlmodel import Field, SQLModel

from where_to_go.about import APP_NAME, VERSION
from where_to_go.api import releases as release_routes
from where_to_go.api.errors import validation_error
from where_to_go.api.origin import SameOriginOnly
from where_to_go.calendar_file import EventCalendarFile
from where_to_go.claude_login import SIGN_IN_HINT, ClaudeLogin, ClaudeSignIn
from where_to_go.cities import BusyCityError, CityError, DuplicateCityError
from where_to_go.container import Container
from where_to_go.feed import FeedFilter, Occurrence, PlanFilter
from where_to_go.launcher.config import InstanceConfig
from where_to_go.models import (
    IMAGE_ROUTE,
    City,
    CityChange,
    CityContents,
    CityPublic,
    CityRequest,
    DevNoteBase,
    DevNotePublic,
    Event,
    EventPublic,
    Mark,
    MentionPublic,
    PlacePublic,
    PotentialSourceMark,
    PotentialSourcePublic,
    Source,
    SourcePublic,
    SourcePause,
    SourceStatusChange,
    TagBase,
    TagOrder,
    TagPublic,
    TagVisibility,
)
from where_to_go.phone_page.github import PublishError
from where_to_go.phone_page.service import PhonePageState
from where_to_go.refresh import RefreshProgress
from where_to_go.search import SearchQuery
from where_to_go.settings import AppSettings, SettingsChange
from where_to_go.statistics import CityStats
from where_to_go.sources import DuplicateSourceError
from where_to_go.telegram import SourceError
from where_to_go.web_sources import SitePreview

DESCRIPTION = """
Local backend of «What To Do». It reads public Telegram channels, Claude turns posts into event cards
and merges the same event announced by several channels into one card.

**First run.** The app starts empty: add a city (`POST /cities`, the first one becomes active),
add channels (`POST /sources`), press refresh (`POST /refresh`) and poll `GET /refresh` until `running` is false.

**Active city.** Sources, the feed, places and refresh work with the active city only (`active_city_id` in settings).
Without a city these answer 409. Tags and the priority wish are shared by all cities; the card language is each city's own.

**Errors** come as `{"detail": "<text ready to show>"}`.
"""


class ApiTag(StrEnum):
    SETTINGS = "settings"
    SOURCES = "sources"
    TAGS = "tags"
    EVENTS = "events"
    REFRESH = "refresh"
    STATS = "stats"
    PHONE_PAGE = "phone page"


TAG_HELP = {
    ApiTag.SETTINGS: "Settings and cities",
    ApiTag.SOURCES: "Telegram channels and websites of the active city",
    ApiTag.TAGS: "The fixed list of tags Claude may put on cards",
    ApiTag.EVENTS: "The feed, a card, marks, manual merge and split",
    ApiTag.REFRESH: "Collect new posts and turn them into cards",
    ApiTag.STATS: "Counts of what was read, found and marked",
    ApiTag.PHONE_PAGE: "The encrypted page of upcoming plans on GitHub Pages, for the phone",
}


class ClaudeSignInView(BaseModel):
    state: ClaudeSignIn
    hint: str
    signing_in: bool = Field(default=False, description="A sign-in started from the app waits for the browser")
    page_url: str | None = Field(default=None, description="The sign-in page to open by hand; it shows a code to paste")
    error: str | None = Field(default=None, description="Why the last sign-in from the app failed")


class SignInCodeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2000, description="The code the sign-in page shows")


class ErrorDetail(BaseModel):
    detail: str = Field(description="What went wrong, ready to show")


class PhonePageRequest(BaseModel):
    repository: str = Field(description="The GitHub repository to publish to, as owner/name")
    token: str | None = Field(default=None, description="A GitHub token with access to it; empty keeps the saved one")
    password: str | None = Field(default=None, description="Opens the page on the phone; empty keeps the saved one")


class SourceRequest(SQLModel):
    link: str = Field(
        min_length=1,
        description="A public channel (t.me/name, @name, name) or a link to any event page of a website with an afisha",
        schema_extra={"examples": ["t.me/londonevents"]},
    )
    title: str | None = Field(default=None, description="Empty: the channel's own title is used")


class SourceRename(SQLModel):
    title: str = Field(min_length=1)


class MergeRequest(SQLModel):
    other_event_id: int = Field(description="This card is merged into the one in the path and disappears")


class SplitRequest(SQLModel):
    mention_id: int = Field(description="The mention to move into a card of its own")


ContainerFactory = Callable[[], Container]


def _container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(_container)]


def _active_city(c: ContainerDep) -> City:
    city = c.cities.active()
    if city is None:
        raise HTTPException(409, "Add a city first")
    return city


def _source(source_id: int, c: ContainerDep) -> Source:
    try:
        return c.sources.get(source_id)
    except KeyError:
        raise HTTPException(404, "Source not found") from None


@contextmanager
def _city_errors() -> Iterator[None]:
    try:
        yield
    except KeyError:
        raise HTTPException(404, "City not found") from None
    except (DuplicateCityError, BusyCityError) as error:
        raise HTTPException(409, str(error)) from None
    except CityError as error:
        raise HTTPException(422, str(error)) from None


def _public(c: Container, event: Event) -> EventPublic:
    return EventPublic.of(event, c.cities.get(event.city_id))


def _event(event_id: int, c: ContainerDep) -> Event:
    try:
        return c.events.get(event_id)
    except KeyError:
        raise HTTPException(404, "Event not found") from None


CityDep = Annotated[City, Depends(_active_city)]
SourceDep = Annotated[Source, Depends(_source)]
EventDep = Annotated[Event, Depends(_event)]


def create_app(container_factory: ContainerFactory) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = container_factory()
        app.state.container.phone_page.start()
        yield
        await app.state.container.close()

    app = FastAPI(
        title=APP_NAME,
        version=VERSION,
        description=DESCRIPTION,
        openapi_tags=[{"name": tag.value, "description": text} for tag, text in TAG_HELP.items()]
        + [{"name": release_routes.TAG, "description": release_routes.TAG_HELP}],
        lifespan=lifespan,
    )
    app.add_middleware(SameOriginOnly)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ValidationError, validation_error)

    # ---------- settings and cities ----------

    @app.get("/settings", response_model=AppSettings, tags=[ApiTag.SETTINGS])
    def get_settings(c: ContainerDep):
        """All settings of the app."""
        return c.settings.load()

    @app.patch("/settings", response_model=AppSettings, tags=[ApiTag.SETTINGS])
    def patch_settings(body: SettingsChange, c: ContainerDep):
        """Changes the settings that are sent. Switching the active city switches the feed and the sources."""
        change = body.model_dump(exclude_unset=True, exclude_none=True)
        if "active_city_id" in change and c.cities.get(change["active_city_id"]) is None:
            raise HTTPException(404, "City not found")
        return c.settings.update(**change)

    @app.get("/settings/defaults", response_model=AppSettings, tags=[ApiTag.SETTINGS])
    def default_settings():
        """What every setting is out of the box; resetting a setting takes the value from here."""
        return AppSettings()

    @app.get("/cities", response_model=list[CityPublic], tags=[ApiTag.SETTINGS])
    def list_cities(c: ContainerDep):
        """Every city the user has added; old ones stay after a move. The active one is `active_city_id` in settings."""
        return c.cities.all()

    @app.post("/cities", response_model=CityPublic, status_code=201, tags=[ApiTag.SETTINGS])
    def add_city(body: CityRequest, c: ContainerDep):
        """Adds a city. The first city becomes active; later ones are activated with `PATCH /settings`.
        The first city of an empty app also brings the default tags, in its card language (English unless Russian).

        409: a city of this name is there already. 422: unknown time zone."""
        with _city_errors():
            return c.city_catalog.add(body)

    @app.patch("/cities/{city_id}", response_model=CityPublic, tags=[ApiTag.SETTINGS])
    def change_city(city_id: int, body: CityChange, c: ContainerDep):
        """Changes the fields that are sent. A new card language reads the city's recent posts again at its next refresh.

        409: another city has this name. 422: unknown time zone."""
        with _city_errors():
            return c.city_catalog.change(city_id, body)

    @app.get("/cities/{city_id}/contents", response_model=CityContents, tags=[ApiTag.SETTINGS])
    def city_contents(city_id: int, c: ContainerDep):
        """What deleting the city would delete with it."""
        with _city_errors():
            return c.city_catalog.contents(city_id)

    @app.delete("/cities/{city_id}", status_code=204, tags=[ApiTag.SETTINGS])
    def delete_city(city_id: int, c: ContainerDep):
        """Deletes the city with its sources, their posts, its cards and marks. Another city becomes active, if there is one.

        409: a refresh is running."""
        with _city_errors():
            c.city_catalog.delete(city_id)

    # ---------- sources ----------

    @app.get("/sources", response_model=list[SourcePublic], tags=[ApiTag.SOURCES])
    def list_sources(c: ContainerDep, city: CityDep):
        """Channels of the active city with the result of their last refresh."""
        return c.sources.in_city(city.id)

    @app.post("/sources", response_model=SourcePublic, status_code=201, tags=[ApiTag.SOURCES])
    async def add_source(body: SourceRequest, c: ContainerDep, city: CityDep):
        """Adds a public Telegram channel or a website to the active city. Its posts or events are read on the next refresh.

        422: not a channel or event page link, the channel is closed, or the site cannot be read. 409: already added.
        """
        try:
            return await c.catalog.add(city, body.link, body.title)
        except DuplicateSourceError as error:
            raise HTTPException(409, str(error)) from None
        except SourceError as error:
            raise HTTPException(422, str(error)) from None

    @app.post("/sources/preview", response_model=SitePreview, tags=[ApiTag.SOURCES])
    async def preview_source(body: SourceRequest, c: ContainerDep, city: CityDep):
        """What adding the link would add: a channel's title, or a website's name, its event pages and a few examples.

        422: the link is not a channel, or the site has no list of pages or no event markup.
        """
        try:
            return await c.catalog.preview(city, body.link)
        except DuplicateSourceError as error:
            raise HTTPException(409, str(error)) from None
        except SourceError as error:
            raise HTTPException(422, str(error)) from None

    @app.patch("/sources/{source_id}", response_model=SourcePublic, tags=[ApiTag.SOURCES])
    def rename_source(body: SourceRename, c: ContainerDep, source: SourceDep):
        """Renames a source."""
        return c.sources.change(source.id, title=body.title.strip())

    @app.put("/sources/{source_id}/status", response_model=SourcePublic, tags=[ApiTag.SOURCES])
    def mark_source(body: SourceStatusChange, c: ContainerDep, source: SourceDep):
        """Sets the user's mark on a source: new or favorite. It changes nothing in the refresh or the feed."""
        return c.sources.change(source.id, status=body.status)

    @app.put("/sources/{source_id}/paused", response_model=SourcePublic, tags=[ApiTag.SOURCES])
    def pause_source(body: SourcePause, c: ContainerDep, source: SourceDep):
        """Pauses or resumes a source. Refresh skips a paused one, so no new posts come from it; its cards stay."""
        return c.sources.change(source.id, paused=body.paused)

    @app.delete("/sources/{source_id}", status_code=204, tags=[ApiTag.SOURCES])
    def delete_source(c: ContainerDep, source: SourceDep):
        """Deletes a source with its posts. Cards only it announced disappear; shared cards lose its post."""
        c.catalog.delete(source.id)

    @app.get("/potential-sources", response_model=list[PotentialSourcePublic], tags=[ApiTag.SOURCES])
    def list_potential_sources(c: ContainerDep, city: CityDep):
        """Channels the active city's posts forward from or link to, not added as sources; most pointed to first.
        Processed ones are included: the client hides them. They are found when posts are read; adding one is up to the user."""
        return c.potential_sources.in_city(city.id)

    @app.post("/potential-sources/{potential_id}/source", response_model=SourcePublic, status_code=201, tags=[ApiTag.SOURCES])
    async def adopt_potential_source(potential_id: int, c: ContainerDep, city: CityDep):
        """Adds the channel as a source of the active city and marks it processed. Already a source: it is just marked.

        422: the channel is closed or has no web preview; nothing changes and it stays in the list.
        """
        try:
            return await c.potential_sources.adopt(city, potential_id)
        except KeyError:
            raise HTTPException(404, "Potential source not found") from None
        except SourceError as error:
            raise HTTPException(422, str(error)) from None

    @app.put("/potential-sources/{potential_id}/processed", status_code=204, tags=[ApiTag.SOURCES])
    def mark_potential_source(potential_id: int, body: PotentialSourceMark, c: ContainerDep):
        """Marks a potential source processed or not. A processed one takes no more posts, so it never comes back."""
        try:
            c.potential_sources.mark(potential_id, body.processed)
        except KeyError:
            raise HTTPException(404, "Potential source not found") from None

    # ---------- tags ----------

    @app.get("/tags", response_model=list[TagPublic], tags=[ApiTag.TAGS])
    def list_tags(c: ContainerDep):
        """Tags in display order; the fallback tag is always last."""
        return c.tags.all()

    @app.post("/tags", response_model=TagPublic, status_code=201, tags=[ApiTag.TAGS])
    def add_tag(body: TagBase, c: ContainerDep):
        """Adds a tag. Claude uses it for posts read from now on. 409: there is a tag of this name already."""
        try:
            return c.tags.add(body.name.strip())
        except ValueError as error:
            raise HTTPException(409, str(error)) from None

    @app.patch("/tags/{tag_id}", response_model=TagPublic, tags=[ApiTag.TAGS])
    def rename_tag(tag_id: int, body: TagBase, c: ContainerDep):
        """Renames a tag everywhere, on existing cards too; the fallback tag as well. 422: another tag has this name."""
        try:
            return c.tags.rename(tag_id, body.name.strip())
        except KeyError:
            raise HTTPException(404, "Tag not found") from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.put("/tags/order", response_model=list[TagPublic], tags=[ApiTag.TAGS])
    def reorder_tags(body: TagOrder, c: ContainerDep):
        """Sets the display order of the tags: cards show their tags in it. 422 unless every tag is listed once."""
        try:
            return c.tags.reorder(body.ids)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.put("/tags/{tag_id}/hidden", response_model=TagPublic, tags=[ApiTag.TAGS])
    def hide_tag(tag_id: int, body: TagVisibility, c: ContainerDep):
        """Blacklists a tag or takes it off the list. Cards marked by the user are shown whatever their tags."""
        try:
            return c.tags.set_hidden(tag_id, body.hidden)
        except KeyError:
            raise HTTPException(404, "Tag not found") from None

    # ---------- events ----------

    @app.get("/events", response_model=list[Occurrence], tags=[ApiTag.EVENTS])
    def feed(
        c: ContainerDep,
        city: CityDep,
        start: Annotated[date | None, Query(description="First day; default: today in the city's time zone, or the earliest event when only end is given")] = None,
        end: Annotated[date | None, Query(description="Last day, inclusive; default: as far as the city has dated events")] = None,
        tags: Annotated[list[str], Query(description="Any of these tags; repeat the parameter for several")] = [],
        sources: Annotated[list[int], Query(description="Cards that have a post from any of these sources")] = [],
        plans: Annotated[list[PlanFilter], Query(description="Only cards with these plans; none = not marked yet. Default: all")] = [],
        only_timed: Annotated[bool, Query(description="Only events with a known date and time")] = False,
        hide_multiday: Annotated[bool, Query(description="Hide exhibitions, festivals and other multiday events")] = False,
        only_priority: Annotated[bool, Query(description="Only events Claude flagged as fitting the priority wish from settings")] = False,
        search: Annotated[
            str,
            Query(
                description="Words to find in the title, description, venue, address and tags. Each word may be any part "
                "of a word, case does not matter, one typo is forgiven, and the Cyrillic letters that differ only by dots count as one. "
                "When nothing is found, the words are tried once more as if typed with the Russian and English keyboard layouts swapped"
            ),
        ] = "",
    ):
        """The feed: cards laid out on days, sorted by day, then time; unknown time and multiday events go last in a day.
        Unmarked cards with a blacklisted tag are left out."""
        first = start or (c.feed.earliest(city.id) if end else None) or datetime.now(ZoneInfo(city.timezone)).date()
        criteria = FeedFilter(
            start=first,
            end=end,
            tags=frozenset(tags),
            hidden_tags=c.tags.hidden(),
            source_ids=frozenset(sources),
            only_timed=only_timed,
            hide_multiday=hide_multiday,
            only_priority=only_priority,
            plans=frozenset(plans),
            search=SearchQuery(search),
        )
        return c.feed.occurrences(city, criteria)

    @app.get("/events/{event_id}", response_model=EventPublic, tags=[ApiTag.EVENTS])
    def event_card(c: ContainerDep, event: EventDep):
        """One card."""
        return _public(c, event)

    @app.get("/events/{event_id}/mentions", response_model=list[MentionPublic], tags=[ApiTag.EVENTS])
    def event_mentions(c: ContainerDep, event: EventDep):
        """The original posts a card is built from: the organizer's first, then the most detailed, then the newest.
        Each comes with its photos, what Claude read on them, and the lines about this event."""
        return c.originals.present(c.mentions.of_event(event.id))

    @app.get(
        "/events/{event_id}/calendar.ics",
        tags=[ApiTag.EVENTS],
        response_class=Response,
        responses={200: {"content": {EventCalendarFile.MEDIA_TYPE: {}}}},
    )
    def calendar_file(c: ContainerDep, event: EventDep):
        """The card as an .ics file for Apple Calendar, Google Calendar or Outlook.
        A timed event is put in for two hours, since posts give no end time."""
        mentions = c.mentions.of_event(event.id)
        file = EventCalendarFile(event, c.cities.get(event.city_id), mentions[-1].post_url if mentions else None)
        return Response(
            file.render(),
            media_type=EventCalendarFile.MEDIA_TYPE,
            headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
        )

    @app.put("/events/{event_id}/mark", response_model=EventPublic, tags=[ApiTag.EVENTS])
    def set_mark(body: Mark, c: ContainerDep, event: EventDep):
        """Sets interest and plan of a card. Both fields are written as sent: null clears a value."""
        return _public(c, c.events.set_mark(event.id, body))

    @app.post("/events/{event_id}/dev-notes", response_model=DevNotePublic, status_code=201, tags=[ApiTag.EVENTS])
    def add_dev_note(body: DevNoteBase, c: ContainerDep, event: EventDep):
        """Saves the developer's note about a card. Notes are only collected: the app never shows them."""
        text = body.text.strip()
        if not text:
            raise HTTPException(422, "The note is empty")
        return c.dev_notes.add(event.id, text)

    @app.post("/events/{event_id}/merge", response_model=EventPublic, tags=[ApiTag.EVENTS])
    def merge(body: MergeRequest, c: ContainerDep, event: EventDep):
        """The user says two cards are one event: `other_event_id` joins this card and is deleted.
        Claude never undoes a manual merge."""
        _event(body.other_event_id, c)
        try:
            c.cards.merge(event.id, body.other_event_id)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return _public(c, c.events.get(event.id))

    @app.post("/events/{event_id}/split", response_model=EventPublic, tags=[ApiTag.EVENTS])
    def split(body: SplitRequest, c: ContainerDep, event: EventDep):
        """Moves one mention out into a card of its own and returns the new card.
        Claude never undoes a manual split. 422: the card has a single source."""
        try:
            return _public(c, c.events.get(c.cards.split(event.id, body.mention_id)))
        except KeyError:
            raise HTTPException(404, "This event has no such source") from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None

    @app.get("/places", response_model=list[PlacePublic], tags=[ApiTag.EVENTS])
    def places(c: ContainerDep, city: CityDep):
        """Places without a date found in posts; they do not appear in the feed."""
        return c.places.in_city(city.id)

    @app.get(IMAGE_ROUTE + "/{name}", tags=[ApiTag.EVENTS], response_class=FileResponse)
    def image(name: str, c: ContainerDep):
        """A card image; `image_url` of a card points here."""
        path = c.images.path(name)
        if path is None:
            raise HTTPException(404)
        return FileResponse(path)

    # ---------- refresh ----------

    @app.post("/refresh", response_model=RefreshProgress, status_code=202, tags=[ApiTag.REFRESH])
    async def start_refresh(c: ContainerDep, city: CityDep):
        """Starts a refresh of the active city's sources (only that city's) in the background and returns at once.
        A second call while one runs returns the running one."""
        return c.refresh.start()

    @app.get("/refresh", response_model=RefreshProgress, tags=[ApiTag.REFRESH])
    def refresh_status(c: ContainerDep):
        """Progress of the current or the last refresh; poll it while `running` is true."""
        return c.refresh.progress

    def sign_in_view(c: Container) -> ClaudeSignInView:
        progress = c.claude_sign_in.progress()
        return ClaudeSignInView(
            state=ClaudeLogin().check(), hint=SIGN_IN_HINT, signing_in=progress.running, page_url=progress.page_url, error=progress.error
        )

    @app.get("/claude/sign-in", response_model=ClaudeSignInView, tags=[ApiTag.REFRESH])
    def claude_sign_in(c: ContainerDep):
        """Whether Claude Code, which reads the posts, is signed in, and how a sign-in started here goes."""
        return sign_in_view(c)

    @app.post("/claude/sign-in", response_model=ClaudeSignInView, tags=[ApiTag.REFRESH])
    def start_claude_sign_in(c: ContainerDep):
        """Opens Claude's sign-in page in the browser; poll `GET /claude/sign-in` until `state` is signed_in."""
        c.claude_sign_in.start()
        return sign_in_view(c)

    @app.post("/claude/sign-in/code", response_model=ClaudeSignInView, tags=[ApiTag.REFRESH])
    def submit_claude_sign_in_code(request: SignInCodeRequest, c: ContainerDep):
        """Finishes the sign-in with the code the sign-in page shows. 409: no sign-in waits for a code."""
        if not c.claude_sign_in.submit_code(request.code):
            raise HTTPException(409, "No sign-in is waiting for a code. Press Sign in again")
        return sign_in_view(c)

    # ---------- statistics ----------

    @app.get("/stats", response_model=CityStats, tags=[ApiTag.STATS])
    def statistics(c: ContainerDep, city: CityDep):
        """What the active city's posts gave: posts and photos read, events found and merged, the user's marks,
        tags, sources and posts per week."""
        return c.statistics.of_city(city)

    # ---------- phone page ----------

    @app.get("/phone-page", response_model=PhonePageState, tags=[ApiTag.PHONE_PAGE])
    def phone_page(c: ContainerDep):
        """Whether the phone page is on, where it lives and how its last publish went. Never returns the token or password."""
        return c.phone_page.state()

    @app.put(
        "/phone-page",
        response_model=PhonePageState,
        tags=[ApiTag.PHONE_PAGE],
        responses={422: {"model": ErrorDetail, "description": "The request is invalid, GitHub refused, or the plans could not be published"}},
    )
    async def turn_phone_page_on(body: PhonePageRequest, c: ContainerDep):
        """Checks the repository, publishes the plans and keeps them fresh. An empty token or password keeps the saved one. 422: GitHub refused."""
        try:
            return await c.phone_page.turn_on(body.repository, body.token, body.password)
        except PublishError as error:
            raise HTTPException(422, str(error)) from None

    @app.delete(
        "/phone-page",
        response_model=PhonePageState,
        tags=[ApiTag.PHONE_PAGE],
        responses={422: {"model": ErrorDetail, "description": "GitHub could not replace the page; the phone page is off anyway"}},
    )
    async def turn_phone_page_off(c: ContainerDep):
        """Replaces the published page with an empty one. The page is off even when 422 says GitHub could not be reached."""
        try:
            return await c.phone_page.turn_off()
        except PublishError as error:
            raise HTTPException(422, str(error)) from None

    @app.post(
        "/phone-page/publish",
        response_model=PhonePageState,
        tags=[ApiTag.PHONE_PAGE],
        responses={409: {"model": ErrorDetail, "description": "The phone page is off"}},
    )
    async def publish_phone_page(c: ContainerDep):
        """Publishes the plans now, ignoring the ten minute pause. A failure lands in `last_error`. 409: the page is off."""
        try:
            return await c.phone_page.publish_now()
        except PublishError as error:
            raise HTTPException(409, str(error)) from None

    app.include_router(release_routes.router)
    return app


def default_data_dir() -> Path:
    return InstanceConfig.default_data_dir()
