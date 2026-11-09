"""Every entity of the app, described once.

Each entity follows the SQLModel pattern: a base class declares its fields (with the descriptions Claude reads),
the table adds what storage needs (keys, links), the public model adds what the API computes. Facts about an
event are declared once, in EventFacts, and shared by what Claude extracts and by the card.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from datetime import date as Day
from enum import StrEnum
from typing import Any
from urllib.parse import quote_plus

from dateutil.rrule import rrulestr
from pydantic import ConfigDict, TypeAdapter, computed_field, model_validator
from sqlalchemy import JSON, Column, UniqueConstraint
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, Relationship, SQLModel

IMAGE_ROUTE = "/images"
INTEREST_MAX = 5


class TelegramUrls:
    BASE = "https://t.me"

    @classmethod
    def channel(cls, handle: str) -> str:
        return f"{cls.BASE}/{handle}"

    @classmethod
    def preview(cls, handle: str) -> str:
        return f"{cls.BASE}/s/{handle}"

    @classmethod
    def post(cls, handle: str, number: int) -> str:
        return f"{cls.BASE}/{handle}/{number}"


class EventKind(StrEnum):
    SINGLE = "single"
    MULTIDAY = "multiday"
    RECURRING = "recurring"


class UpdateKind(StrEnum):
    ANNOUNCEMENT = "announcement"
    RESCHEDULE = "reschedule"
    CANCELLATION = "cancellation"
    DETAILS = "details"


class Plan(StrEnum):
    MAYBE = "maybe"
    SURE = "sure"
    NO = "no"
    WENT = "went"

    @property
    def is_going(self) -> bool:
        return self in (Plan.MAYBE, Plan.SURE)


class SourceKind(StrEnum):
    TELEGRAM = "telegram"


class ConflictField(StrEnum):
    START_DATE = "start_date"
    START_TIME = "start_time"


class Typed(TypeDecorator):
    """A JSON column holding any pydantic-typed value; the type is given once, on the field."""

    impl = JSON
    cache_ok = True

    def __init__(self, python_type: Any) -> None:
        super().__init__()
        self._adapter = TypeAdapter(python_type)

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return None if value is None else self._adapter.dump_python(value, mode="json")

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return None if value is None else self._adapter.validate_python(value)


def json_field(python_type: Any, **kwargs: Any) -> Any:
    return Field(sa_type=Typed(python_type), **kwargs)


class Public(SQLModel):
    """An API answer: every field with a default is still always there, and the schema says so."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


# ---------- an event ----------


class EventFacts(SQLModel):
    """What a post says about an event. Claude fills these in; a card shows them."""

    title: str = Field(
        description="Your own short title in the description language that says what the event is, understandable without the description"
    )
    original_title: str = Field(description="The name as the post gives it, in the post's language")
    description: str = Field(
        description="2–4 sentences in the description language: what happens and what it is like. Keep the author's manner and tone, "
        "do not advertise, do not repeat date, time, place or price"
    )
    kind: EventKind = Field(
        description="single: one date; multiday: runs over a period (exhibition, festival) from start_date to end_date; "
        "recurring: a regular schedule described by rrule"
    )
    start_date: Day = Field(
        index=True,
        description="Resolve relative dates against the publication date; without a year, the nearest date not long before it. "
        "For recurring events: the first occurrence on or after the publication date",
    )
    end_date: Day | None = Field(default=None, description="multiday only")
    start_time: time | None = Field(default=None, description="Local time; null when the post does not say. Do not guess")
    rrule: str | None = Field(default=None, description='recurring only: an RFC 5545 RRULE body such as "FREQ=WEEKLY;BYDAY=TU"')
    venue: str | None = Field(default=None, description="The venue's name as the post gives it")
    address: str | None = Field(default=None, description="The address as the post gives it")
    price: float | None = Field(
        default=None,
        ge=0,
        description="The price as a number: 0 when free, the lowest one when the post gives several, null when it does not say "
        "or the entry is a donation of any size",
    )
    currency: str | None = Field(default=None, description="ISO 4217 code of the price, e.g. RSD or EUR; null when price is null or 0")
    tags: list[str] = json_field(list[str], default_factory=list, description="One or two tags from the allowed list")

    @model_validator(mode="before")
    @classmethod
    def _one_shape_per_kind(cls, data: Any) -> Any:
        """end_date belongs to multiday events only, rrule to recurring ones; anything else becomes a single event."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        kind = data.get("kind")
        start, end, rule = data.get("start_date"), data.get("end_date"), data.get("rrule")
        if kind == EventKind.MULTIDAY and not (start and end and str(end) > str(start)):
            kind = EventKind.SINGLE
        if kind == EventKind.RECURRING and not _valid_rule(rule, start):
            kind = EventKind.SINGLE
        data["kind"] = kind
        if kind != EventKind.MULTIDAY:
            data["end_date"] = None
        if kind != EventKind.RECURRING:
            data["rrule"] = None
        if not data.get("price"):
            data["currency"] = None
        return data


def _valid_rule(rule: Any, start: Any) -> bool:
    if not rule or not start:
        return False
    try:
        rrulestr(str(rule), dtstart=datetime.fromisoformat(str(start)))
    except (ValueError, TypeError):
        return False
    return True


class ExtractedEvent(EventFacts):
    """One event as one post describes it."""

    update_kind: UpdateKind = Field(
        default=UpdateKind.ANNOUNCEMENT,
        description="announcement: a normal announcement; reschedule: moves an event announced earlier (give the new date and time); "
        "cancellation: cancels one; details: only adds details to one announced earlier",
    )
    from_organizer: bool = Field(
        default=False, description="true when the channel itself organizes or hosts the event, false for afisha and repost channels"
    )


class Mark(SQLModel):
    """What the user decided about an event: how interesting it is, and whether they are going."""

    interest: int | None = Field(default=None, ge=1, le=INTEREST_MAX)
    plan: Plan | None = None

    @computed_field
    @property
    def is_going(self) -> bool:
        return self.plan is not None and self.plan.is_going


class Conflict(SQLModel):
    field: ConflictField
    values: list[str] = Field(description="Every value the sources give; the card shows the first one")


class EventCard(EventFacts, Mark):
    """A card: the facts its posts agree on, the user's mark, and what the sources disagree about."""

    is_cancelled: bool = False
    conflicts: list[Conflict] = json_field(list[Conflict], default_factory=list, description="Sources disagree on these")
    source_ids: list[int] = json_field(list[int], default_factory=list)
    image_path: str | None = Field(default=None, exclude=True)


class Event(EventCard, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    city_id: int = Field(foreign_key="cities.id", index=True)
    marked_at: datetime | None = None


class EventPublic(EventCard, Public):
    id: int

    @computed_field
    @property
    def image_url(self) -> str | None:
        return f"{IMAGE_ROUTE}/{self.image_path}" if self.image_path else None

    @computed_field
    @property
    def place(self) -> str | None:
        """The venue and the address as one line, or whichever is known."""
        return ", ".join(dict.fromkeys(p for p in (self.venue, self.address) if p)) or None

    @computed_field
    @property
    def map_url(self) -> str | None:
        target = self.address or self.venue
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(target)}" if target else None


# ---------- cities, sources, posts, tags ----------


class CityBase(SQLModel):
    name: str = Field(unique=True, min_length=1, schema_extra={"examples": ["Белград"]})
    timezone: str = Field(
        description="IANA time zone, e.g. Europe/Belgrade; «today» in the feed is counted in it", schema_extra={"examples": ["Europe/Belgrade"]}
    )


class City(CityBase, table=True):
    __tablename__ = "cities"

    id: int | None = Field(default=None, primary_key=True)


class CityPublic(CityBase, Public):
    id: int


class SourceBase(SQLModel):
    kind: SourceKind = SourceKind.TELEGRAM
    handle: str
    title: str = Field(description="The name the user gave, or the channel's own title")
    last_refreshed_at: datetime | None = None
    last_error: str | None = Field(default=None, description="Shown next to the source; null when the last refresh went fine")
    events_found: int = Field(default=0, description="Cards this source contributes to")


class Source(SourceBase, table=True):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("kind", "handle", "city_id"),)

    id: int | None = Field(default=None, primary_key=True)
    city_id: int = Field(foreign_key="cities.id", index=True)


class SourcePublic(SourceBase, Public):
    id: int

    @computed_field
    @property
    def url(self) -> str:
        return TelegramUrls.channel(self.handle)


class Post(SQLModel, table=True):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("source_id", "external_id"),)

    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="sources.id", ondelete="CASCADE", index=True)
    external_id: int
    url: str
    published_at: datetime
    text: str
    image_paths: list[str] = json_field(list[str], default_factory=list)
    processed_at: datetime | None = Field(default=None, index=True)
    process_error: str | None = None

    source: Source = Relationship(sa_relationship_kwargs={"lazy": "joined"})


class TagBase(SQLModel):
    name: str = Field(unique=True, min_length=1, schema_extra={"examples": ["Танцы"]})


class Tag(TagBase, table=True):
    __tablename__ = "tags"

    id: int | None = Field(default=None, primary_key=True)
    position: int = 0
    is_fallback: bool = False


class TagPublic(TagBase, Public):
    id: int
    is_fallback: bool = Field(description="Put by Claude when no tag fits; always last, cannot be renamed")


# ---------- mentions and places ----------


class Mention(SQLModel, table=True):
    """One event as one post announced it; a card is built from its mentions."""

    __tablename__ = "mentions"
    __table_args__ = (UniqueConstraint("post_id", "item_index"),)

    id: int | None = Field(default=None, primary_key=True)
    post_id: int = Field(foreign_key="posts.id", ondelete="CASCADE", index=True)
    event_id: int | None = Field(default=None, foreign_key="events.id", ondelete="SET NULL", index=True)
    item_index: int
    data: ExtractedEvent = json_field(ExtractedEvent)
    image_index: int | None = None
    locked: bool = False

    post: Post = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    @property
    def source_id(self) -> int:
        return self.post.source_id

    @property
    def source_title(self) -> str:
        return self.post.source.title

    @property
    def post_url(self) -> str:
        return self.post.url

    @property
    def post_text(self) -> str:
        return self.post.text

    @property
    def published_at(self) -> datetime:
        return self.post.published_at

    @property
    def image_path(self) -> str | None:
        images = self.post.image_paths
        return images[self.image_index] if self.image_index is not None and self.image_index < len(images) else None


class MentionPublic(Public):
    """One original post behind a card."""

    id: int = Field(description="Pass it to split to move this post into a card of its own")
    data: ExtractedEvent
    locked: bool = Field(description="Placed by the user; Claude never moves it")
    source_id: int
    source_title: str
    post_url: str
    post_text: str
    published_at: datetime


class ExtractedPlace(SQLModel):
    """A place with no date: a bar, a climbing gym, a cafe that is simply open."""

    name: str
    address: str | None = None
    description: str = Field(description="One or two sentences in the description language")


class Place(ExtractedPlace, table=True):
    __tablename__ = "places"

    id: int | None = Field(default=None, primary_key=True)
    city_id: int = Field(foreign_key="cities.id", index=True)
    post_id: int = Field(foreign_key="posts.id", ondelete="CASCADE")

    post: Post = Relationship(sa_relationship_kwargs={"lazy": "joined"})

    @property
    def post_url(self) -> str:
        return self.post.url


class PlacePublic(ExtractedPlace, Public):
    id: int
    post_url: str


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: Any = Field(sa_column=Column(JSON, nullable=False))


# ---------- values that are not stored ----------


class CollectedPost(SQLModel):
    """A post as a source gives it, before it is stored."""

    external_id: int
    url: str
    published_at: datetime
    text: str
    image_urls: list[str] = []


class PostReading(SQLModel):
    """What Claude finds in one post; most posts announce nothing and give two empty lists."""

    post_id: int
    events: list[ExtractedEvent] = Field(description="One item per event; a digest post gives one item per event it lists")
    places: list[ExtractedPlace] = []


class Reading(SQLModel):
    posts: list[PostReading]
