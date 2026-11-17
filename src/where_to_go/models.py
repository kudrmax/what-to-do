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

    @classmethod
    def handle_of_post(cls, url: str) -> str | None:
        """The channel a post link names: https://t.me/<handle>/<number>."""
        parts = url.removeprefix(cls.BASE + "/").split("/")
        return parts[0] if url.startswith(cls.BASE + "/") and len(parts) == 2 and parts[1].isdigit() else None


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


class BookingKind(StrEnum):
    REGISTRATION = "registration"
    TICKETS = "tickets"


class SourceKind(StrEnum):
    TELEGRAM = "telegram"
    WEB = "web"
    INSTAGRAM = "instagram"


class SourceStatus(StrEnum):
    """The user's own mark on a source, only to find their way among many."""

    NEW = "new"
    FAVORITE = "favorite"


class ChannelLink(StrEnum):
    LINK = "link"
    FORWARD = "forward"


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


class Booking(SQLModel):
    """Where one signs up for an event or buys a ticket."""

    url: str = Field(description="The link exactly as the post gives it")
    kind: BookingKind = Field(description="registration: a form, a bot or a page to sign up; tickets: a ticket shop")


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
    currency: str | None = Field(default=None, description="ISO 4217 code of the price, e.g. GBP or EUR; null when price is null or 0")
    tags: list[str] = json_field(list[str], default_factory=list, description="One or two tags from the allowed list")
    is_priority: bool = Field(
        default=False,
        sa_column_kwargs={"server_default": "0"},
        description="true when the event fits what the person looks for first (see Priority in the instructions); "
        "false when it does not or nothing is given there",
    )
    booking: Booking | None = json_field(
        Booking | None,
        default=None,
        description="Where to sign up or buy a ticket for this event: a registration form, a booking bot or a ticket shop the post "
        "links to. null when the post gives none; never the channel or another post about the event",
    )

    def facts(self) -> dict[str, Any]:
        """The facts alone, as values: a table model is not validated, so a dump would leave nested facts as dicts."""
        return {name: getattr(self, name) for name in EventFacts.model_fields}

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

    start_date: Day | None = Field(
        description=EventFacts.model_fields["start_date"].description
        + ". null only for a details or cancellation follow-up whose post gives no date at all"
    )
    update_kind: UpdateKind = Field(
        default=UpdateKind.ANNOUNCEMENT,
        description="announcement: a normal announcement; reschedule: moves an event announced earlier (give the new date and time); "
        "cancellation: cancels one; details: only adds details to one announced earlier",
    )
    from_organizer: bool = Field(
        default=False, description="true when the channel itself organizes or hosts the event, false for afisha and repost channels"
    )
    post_lines: list[str] = Field(
        default_factory=list,
        description="The lines of the post text that are about this event, copied exactly. Empty when the whole post is about this one event",
    )

    @model_validator(mode="after")
    def _only_follow_ups_go_without_a_date(self) -> ExtractedEvent:
        if self.start_date is None and self.update_kind not in (UpdateKind.DETAILS, UpdateKind.CANCELLATION):
            raise ValueError("only a details or cancellation follow-up may come without a date")
        return self

    @property
    def is_dateless_follow_up(self) -> bool:
        """It is about an event announced earlier and can only join that event's card."""
        return self.start_date is None


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

    def is_dropped_with(self, paused_source_ids: set[int]) -> bool:
        """Only paused sources announce it and the user never marked it: it is no longer shown."""
        unmarked = self.interest is None and self.plan is None
        return unmarked and bool(self.source_ids) and paused_source_ids.issuperset(self.source_ids)


class Event(EventCard, table=True):
    __tablename__ = "events"

    id: int | None = Field(default=None, primary_key=True)
    city_id: int = Field(foreign_key="cities.id", index=True)
    marked_at: datetime | None = None


class EventPublic(EventCard, Public):
    id: int
    city_label: str | None = Field(default=None, exclude=True)

    @classmethod
    def of(cls, event: Event, city: City | None) -> EventPublic:
        return cls.model_validate(event).model_copy(update={"city_label": city.label if city else None})

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
        """The address, or the venue, with the city and country unless the address names the city already."""
        target = self.address or self.venue
        if not target:
            return None
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(CityLabel.pinpoint(target, self.city_label))}"


# ---------- cities, sources, posts, tags ----------


class CityLabel:
    """A city as maps and Claude need it: «London, United Kingdom»."""

    @staticmethod
    def of(name: str, country: str) -> str:
        return ", ".join(part for part in (name.strip(), country.strip()) if part)

    @staticmethod
    def pinpoint(place: str, label: str | None) -> str:
        """A place with its city added, unless it names the city already: an address alone may be in any city."""
        if not label:
            return place
        city = label.split(",")[0].strip()
        return place if city.casefold() in place.casefold() else f"{place}, {label}"


class CityBase(SQLModel):
    name: str = Field(unique=True, min_length=1, schema_extra={"examples": ["London"]})
    country: str = Field(
        default="",
        sa_column_kwargs={"server_default": ""},
        description="Tells apart cities of the same name for Claude and for maps; empty only in cities added before 1.16",
        schema_extra={"examples": ["United Kingdom"]},
    )
    timezone: str = Field(
        description="IANA time zone, e.g. Europe/London; «today» in the feed is counted in it", schema_extra={"examples": ["Europe/London"]}
    )
    card_language: str = Field(
        default="English",
        min_length=1,
        sa_column_kwargs={"server_default": "English"},
        description="Language Claude writes card titles and descriptions in; changing it reads the recent posts again",
        schema_extra={"examples": ["English"]},
    )

    @property
    def label(self) -> str:
        return CityLabel.of(self.name, self.country)


class City(CityBase, table=True):
    __tablename__ = "cities"

    id: int | None = Field(default=None, primary_key=True)


class CityPublic(CityBase, Public):
    id: int


class CityRequest(CityBase):
    country: str = Field(min_length=1, description=CityBase.model_fields["country"].description, schema_extra={"examples": ["United Kingdom"]})


class CityChange(SQLModel):
    """Only the fields that are sent change."""

    name: str | None = Field(default=None, min_length=1)
    country: str | None = Field(default=None, min_length=1)
    timezone: str | None = None
    card_language: str | None = Field(default=None, min_length=1)


class CityContents(Public):
    """What deleting a city deletes with it."""

    sources: int
    events: int
    marked_events: int = Field(description="Cards the user rated or planned to go to")


class SourceBase(SQLModel):
    kind: SourceKind = SourceKind.TELEGRAM
    handle: str
    title: str = Field(description="The name the user gave, or the channel's own title")
    last_refreshed_at: datetime | None = None
    last_error: str | None = Field(default=None, description="Shown next to the source; null when the last refresh went fine")
    events_found: int = Field(default=0, description="Cards this source contributes to")
    status: SourceStatus = Field(
        default=SourceStatus.NEW, sa_column_kwargs={"server_default": SourceStatus.NEW.name}, description="The user's mark: every source starts new"
    )
    paused: bool = Field(
        default=False, sa_column_kwargs={"server_default": "0"}, description="Skipped by refresh: no new posts, its cards stay"
    )


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
        """The channel on t.me, or the site's section with its events."""
        return f"https://{self.handle}" if self.kind == SourceKind.WEB else TelegramUrls.channel(self.handle)


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
    read_with: str | None = Field(default=None, description="Fingerprint of the reading rules the post was last read with")

    source: Source = Relationship(sa_relationship_kwargs={"lazy": "joined"})


class WebSite(SQLModel, table=True):
    """How a website source is read: where its list of pages is and which of them are its events."""

    __tablename__ = "web_sites"

    source_id: int = Field(primary_key=True, foreign_key="sources.id", ondelete="CASCADE")
    sitemap_urls: list[str] = json_field(list[str], default_factory=list, description="The site's sitemaps that list its events")
    prefix: str = Field(description="The site and the section its event pages are in: https://site/ru/events/")
    times_are_local: bool = Field(default=False, description="The site labels its local time as UTC")
    times_settled: bool = Field(
        default=True,
        sa_column_kwargs={"server_default": "1"},
        description="False while no page has told how the site labels its time: in a city on UTC in winter both readings agree",
    )
    horizon_days: int = 30


class WebPage(SQLModel, table=True):
    """A page of a website source, downloaded once: an event with its facts, or a page that is not one.
    Its post, once there is one, has the page's id as external_id."""

    __tablename__ = "web_pages"
    __table_args__ = (UniqueConstraint("source_id", "url"),)

    id: int | None = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="sources.id", ondelete="CASCADE", index=True)
    url: str
    is_event: bool
    start_day: Day | None = Field(default=None, description="In the city's time; all the horizon needs")
    end_day: Day | None = None
    facts: str | None = Field(default=None, description="What Claude reads for this event")
    locality: str | None = Field(default=None, description="The town the page names, as it names it")
    has_facts: bool = Field(default=False, sa_column_kwargs={"server_default": "0"}, description="Pages kept by 1.10.0–1.10.1 have none")
    start_time: time | None = None
    venue: str | None = None
    address: str | None = None
    price: float | None = None
    currency: str | None = None
    online: bool = Field(default=False, sa_column_kwargs={"server_default": "0"})
    fingerprint: str | None = Field(default=None, description="Of the event's own facts: the page around them may change on every visit")
    image_url: str | None = None
    found_at: datetime
    checked_at: datetime


class PageFacts(SQLModel):
    """What an event page states for sure; it wins over what Claude reads from the page's text."""

    start_date: Day
    start_time: time | None = None
    end_date: Day | None = None
    venue: str | None = None
    address: str | None = None
    price: float | None = None
    currency: str | None = None

    def settle(self, event: ExtractedEvent) -> ExtractedEvent:
        """Claude keeps the title, description, tags and how it split the page; the facts are the page's."""
        update: dict[str, Any] = {"start_date": self.start_date, "start_time": self.start_time}
        update |= {k: v for k, v in {"venue": self.venue, "address": self.address}.items() if v}
        if self.price is not None:
            update |= {"price": self.price, "currency": self.currency if self.price else None}
        if event.kind != EventKind.RECURRING:
            runs = self.end_date is not None and self.end_date > self.start_date
            update |= {"kind": EventKind.MULTIDAY if runs else EventKind.SINGLE, "end_date": self.end_date if runs else None}
        return event.model_copy(update=update)


class Locality(SQLModel, table=True):
    """A town a website names, and whether it is the city: so events elsewhere never reach Claude."""

    __tablename__ = "localities"
    __table_args__ = (UniqueConstraint("city_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    city_id: int = Field(foreign_key="cities.id", ondelete="CASCADE", index=True)
    name: str
    in_city: bool


class PhotoTextBase(SQLModel):
    """What a post photo says, transcribed once so posts are read as text."""

    text: str = Field(
        description="All the text on the photo word for word, in its own language. Keep line breaks and structure: "
        'a schedule or a table stays one, one row per line, cells separated by " | ". Do not correct, translate, '
        "summarize or skip small print. Empty when the photo has no text"
    )
    shows: str = Field(
        description='One short sentence in English about what the photo is, e.g. "poster of a tea ceremony", '
        '"weekly schedule", "collage of 12 event posters", "people at a table, no text"'
    )


class PhotoText(PhotoTextBase, table=True):
    __tablename__ = "photo_texts"

    image: str = Field(primary_key=True, description="The stored image file")
    read_with: str = Field(description="Fingerprint of the transcription rules")


class TagBase(SQLModel):
    name: str = Field(unique=True, min_length=1, schema_extra={"examples": ["Dance"]})


class Tag(TagBase, table=True):
    __tablename__ = "tags"

    id: int | None = Field(default=None, primary_key=True)
    position: int = 0
    is_fallback: bool = False
    hidden: bool = Field(default=False, sa_column_kwargs={"server_default": "0"})


class TagPublic(TagBase, Public):
    id: int
    is_fallback: bool = Field(description="Put by Claude when no tag fits; always last")
    hidden: bool = Field(description="Blacklisted: the feed leaves out cards with this tag unless the user marked them")


class TagVisibility(SQLModel):
    hidden: bool


class TagOrder(SQLModel):
    ids: list[int] = Field(description="Every tag but the fallback, in the new display order; the fallback stays last")


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
    def source_kind(self) -> SourceKind:
        return self.post.source.kind

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


class PostPhoto(Public):
    url: str
    text: str | None = Field(default=None, description="What Claude read on the photo; null until it is read")


class MentionPublic(Public):
    """One original post behind a card."""

    id: int = Field(description="Pass it to split to move this post into a card of its own")
    data: ExtractedEvent
    locked: bool = Field(description="Placed by the user; Claude never moves it")
    source_id: int
    source_title: str
    source_kind: SourceKind = Field(description="web: post_url is the event's page on the site")
    post_url: str
    post_text: str
    published_at: datetime
    photos: list[PostPhoto] = Field(default_factory=list, description="Every photo of the post, in its order")
    event_photo: int | None = Field(default=None, description="Index in photos of the one that shows this event")
    event_lines: list[int] = Field(
        default_factory=list, description="Indexes of the post_text lines about this event; empty when the whole post is about it"
    )


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


# ---------- potential sources ----------


class ChannelReference(SQLModel):
    """Another Telegram channel a post points to; a channel the user might want to add."""

    handle: str = Field(description='The channel\'s username without "@", e.g. "london_events"; from a t.me link or an @mention')
    via: ChannelLink = Field(description="forward: the post is forwarded from that channel; link: the post links to it or mentions it")


class PotentialSource(SQLModel, table=True):
    """A channel posts pointed to; it stays until the user marks it processed, then it never comes back."""

    __tablename__ = "potential_sources"
    __table_args__ = (UniqueConstraint("city_id", "handle"),)

    id: int | None = Field(default=None, primary_key=True)
    city_id: int = Field(foreign_key="cities.id", index=True)
    handle: str
    processed: bool = False
    found_at: datetime


class PotentialSourcePost(SQLModel, table=True):
    """A post that pointed to a potential source."""

    __tablename__ = "potential_source_posts"
    __table_args__ = (UniqueConstraint("potential_source_id", "post_id"),)

    id: int | None = Field(default=None, primary_key=True)
    potential_source_id: int = Field(foreign_key="potential_sources.id", ondelete="CASCADE", index=True)
    post_id: int = Field(foreign_key="posts.id", ondelete="CASCADE", index=True)
    via: ChannelLink

    post: Post = Relationship(sa_relationship_kwargs={"lazy": "joined"})


class PotentialSourceOrigin(Public):
    """A post that pointed to the channel."""

    via: ChannelLink
    source_title: str
    post_url: str
    published_at: datetime


class SourceStatusChange(SQLModel):
    status: SourceStatus


class SourcePause(SQLModel):
    paused: bool


class PotentialSourceMark(SQLModel):
    processed: bool = Field(description="The user looked at the channel: added it by hand or decided not to")


class PotentialSourcePublic(Public):
    id: int
    handle: str
    processed: bool
    found_at: datetime
    origins: list[PotentialSourceOrigin] = Field(description="The posts that pointed to it, newest first")

    @computed_field
    @property
    def url(self) -> str:
        return TelegramUrls.channel(self.handle)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: Any = Field(sa_column=Column(JSON, nullable=False))


class DevNoteBase(SQLModel):
    text: str = Field(min_length=1, description="Free text: what to improve about this card or the app")


class DevNote(DevNoteBase, table=True):
    """A developer's note left from a card; it is only collected, never shown in the app."""

    __tablename__ = "dev_notes"

    id: int | None = Field(default=None, primary_key=True)
    event_id: int | None = Field(default=None, index=True)
    created_at: datetime


class DevNotePublic(DevNoteBase, Public):
    id: int
    event_id: int | None
    created_at: datetime


# ---------- values that are not stored ----------


class CollectedPost(SQLModel):
    """A post as a source gives it, before it is stored."""

    external_id: int
    url: str
    published_at: datetime
    text: str
    image_urls: list[str] = []


class EventReading(ExtractedEvent):
    """An event Claude found, with the photo of the post that shows it."""

    photo: int | None = Field(
        description="Index of the post's photo that shows this event: its poster, its card or a poster it shares with other events. "
        "null when no photo shows it"
    )


class PostReading(SQLModel):
    """What Claude finds in one post; most posts announce nothing and give two empty lists."""

    post_id: int
    events: list[EventReading] = Field(description="One item per event; a digest post gives one item per event it lists")
    places: list[ExtractedPlace] = []
    channels: list[ChannelReference] = Field(
        default=[],
        description="Every other Telegram channel or group the post is forwarded from, links to or mentions by @username, even "
        "when it does not look like an afisha: the user decides. Leave out the post's own channel, bots, personal accounts "
        "and private invite links",
    )


class Reading(SQLModel):
    posts: list[PostReading]


class PhotoReading(PhotoTextBase):
    photo: int = Field(description="The photo's number from its caption")


class PhotoReadings(SQLModel):
    photos: list[PhotoReading] = Field(description="One item per photo")
