from __future__ import annotations

import datetime as dt
from datetime import date, datetime, time

from pydantic import BaseModel, Field

from where_to_go.domain import EventKind, Plan, SourceKind, UpdateKind
from where_to_go.refresh import Stage


class CityOut(BaseModel):
    id: int
    name: str
    timezone: str = Field(description="IANA time zone, e.g. Europe/Belgrade; «today» in the feed is counted in it")
    active: bool = Field(description="The feed, sources and refresh work with the active city only")


class CityIn(BaseModel):
    name: str = Field(min_length=1, examples=["Белград"])
    timezone: str = Field(examples=["Europe/Belgrade"])


class SourceOut(BaseModel):
    id: int
    city_id: int
    kind: SourceKind
    title: str = Field(description="The name the user gave, or the channel's own title")
    url: str = Field(examples=["https://t.me/vstrechi_v_belgrade"])
    last_refreshed_at: datetime | None = Field(description="null until the first refresh")
    last_error: str | None = Field(description="Shown to the user next to the source; null when the last refresh went fine")
    events_found: int = Field(description="Cards this source contributes to")


class SourceIn(BaseModel):
    link: str = Field(min_length=1, description="Any form of a public channel link: t.me/name, @name, name", examples=["t.me/vstrechi_v_belgrade"])
    title: str | None = Field(default=None, description="Empty: the channel's own title is used")


class SourcePatch(BaseModel):
    title: str = Field(min_length=1)


class TagOut(BaseModel):
    id: int
    name: str
    is_fallback: bool = Field(description="The «не распознано» tag: Claude puts it when no tag fits; always last")


class TagIn(BaseModel):
    name: str = Field(min_length=1, examples=["Танцы"])


class ConflictOut(BaseModel):
    field: str = Field(description="start_date or start_time")
    values: list[str] = Field(description="Every value the sources give; the card shows the first one", examples=[["19:00", "19:30"]])


class MarkOut(BaseModel):
    interest: int | None = Field(description="1 (not interesting at all) … 5 (very interesting)")
    plan: Plan | None = Field(description="maybe, sure, no, went")


class MarkIn(BaseModel):
    """Both fields are written as sent: null clears a value."""

    interest: int | None = Field(default=None, ge=1, le=5)
    plan: Plan | None = None


class EventOut(BaseModel):
    id: int
    kind: EventKind = Field(description="single: one date; multiday: start_date…end_date; recurring: repeats by `recurrence`")
    title: str = Field(description="Claude's own title in the description language")
    original_title: str = Field(description="The title as the organizer or the channel wrote it")
    description: str = Field(description="Claude's summary in the author's manner; the main element of a card")
    start_date: date = Field(description="For recurring events: the first occurrence")
    end_date: date | None = Field(description="multiday only")
    start_time: time | None = Field(description="null: time is not known yet («время уточняется»)")
    recurrence: str | None = Field(description="RFC 5545 RRULE body, recurring only", examples=["FREQ=WEEKLY;BYDAY=TU"])
    venue: str | None
    address: str | None
    map_url: str | None = Field(description="Google Maps search for the address or venue")
    price: str | None = Field(description="As the post gives it", examples=["800 RSD"])
    tags: list[str]
    image_url: str | None = Field(description="Relative to the API root", examples=["/images/3f2a.jpg"])
    is_cancelled: bool
    conflicts: list[ConflictOut] = Field(description="Sources disagree; show «в источниках расходится»")
    source_ids: list[int]
    mark: MarkOut


class OccurrenceOut(BaseModel):
    date: dt.date = Field(
        description="The day this card is shown on: a recurring event appears once per day, "
        "a multiday one once, on the first day inside the requested range"
    )
    event: EventOut


class MentionOut(BaseModel):
    """One post that announced this event."""

    id: int = Field(description="Pass it to /split to move this source into a card of its own")
    source_id: int
    source_title: str
    post_url: str
    published_at: datetime
    original_title: str
    post_text: str
    from_organizer: bool = Field(description="Posted by the organizer or the venue, not by an afisha")
    update_kind: UpdateKind = Field(description="announcement, reschedule, cancellation or details")


class EventDetailOut(EventOut):
    mentions: list[MentionOut] = Field(description="Original posts, oldest first")


class MergeIn(BaseModel):
    other_event_id: int = Field(description="This card is merged into the one in the path and disappears")


class SplitIn(BaseModel):
    mention_id: int


class RefreshOut(BaseModel):
    stage: Stage = Field(description="idle → collecting → reading → merging → done | failed")
    running: bool
    started_at: datetime | None
    finished_at: datetime | None
    new_posts: int = Field(description="Posts downloaded in this refresh")
    posts_to_read: int = Field(description="Posts Claude reads in this refresh")
    posts_read: int
    events_touched: int = Field(description="Cards created or updated")
    errors: list[str] = Field(description="Human-readable, ready to show")


class PlaceOut(BaseModel):
    """A place without a date (a bar, a climbing gym); kept apart from the feed."""

    id: int
    name: str
    address: str | None
    description: str
    post_url: str
