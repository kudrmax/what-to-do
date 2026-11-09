from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum


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


@dataclass(frozen=True)
class City:
    id: int
    name: str
    timezone: str


@dataclass(frozen=True)
class Source:
    id: int
    city_id: int
    kind: SourceKind
    handle: str
    title: str
    last_refreshed_at: datetime | None = None
    last_error: str | None = None
    last_post_id: int | None = None
    events_found: int = 0

    @property
    def url(self) -> str:
        return f"https://t.me/{self.handle}"


@dataclass(frozen=True)
class Tag:
    id: int
    name: str
    position: int
    is_fallback: bool = False


@dataclass(frozen=True)
class CollectedPost:
    external_id: int
    url: str
    published_at: datetime
    text: str
    image_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class Post:
    id: int
    source_id: int
    external_id: int
    url: str
    published_at: datetime
    text: str
    image_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractedEvent:
    title: str
    original_title: str
    description: str
    kind: EventKind
    start_date: date
    end_date: date | None = None
    start_time: time | None = None
    rrule: str | None = None
    venue: str | None = None
    address: str | None = None
    price: str | None = None
    tags: tuple[str, ...] = ()
    update_kind: UpdateKind = UpdateKind.ANNOUNCEMENT
    from_organizer: bool = False
    image_index: int | None = None


@dataclass(frozen=True)
class ExtractedPlace:
    name: str
    address: str | None
    description: str


@dataclass(frozen=True)
class PostExtraction:
    post_id: int
    events: tuple[ExtractedEvent, ...] = ()
    places: tuple[ExtractedPlace, ...] = ()


@dataclass(frozen=True)
class Mention:
    """One event as a single post described it."""

    id: int
    post_id: int
    event_id: int | None
    item_index: int
    data: ExtractedEvent
    published_at: datetime
    source_id: int
    image_path: str | None
    locked: bool = False


@dataclass(frozen=True)
class Mark:
    interest: int | None = None
    plan: Plan | None = None

    @property
    def is_complete(self) -> bool:
        return self.interest is not None and self.plan is not None

    @property
    def is_dismissed(self) -> bool:
        """The user is not going (or already went): the card leaves the feed, interest or not."""
        return self.plan is not None and not self.plan.is_going


@dataclass(frozen=True)
class Conflict:
    field: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Event:
    id: int
    city_id: int
    kind: EventKind
    title: str
    original_title: str
    description: str
    start_date: date
    end_date: date | None
    start_time: time | None
    rrule: str | None
    venue: str | None
    address: str | None
    price: str | None
    tags: tuple[str, ...]
    image_path: str | None
    is_cancelled: bool
    conflicts: tuple[Conflict, ...] = ()
    source_ids: tuple[int, ...] = ()
    mark: Mark = field(default_factory=Mark)
