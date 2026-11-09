from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, time
from typing import Any
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from where_to_go.domain import (
    City,
    EventKind,
    ExtractedEvent,
    ExtractedPlace,
    Post,
    PostExtraction,
    Source,
    UpdateKind,
)
from where_to_go.llm import JsonLlm

_NULLABLE_STRING = {"type": ["string", "null"]}

_EVENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title", "original_title", "description", "kind", "start_date", "end_date", "start_time", "rrule",
        "venue", "address", "price", "tags", "update_kind", "from_organizer",
    ],
    "properties": {
        "title": {"type": "string"},
        "original_title": {"type": "string"},
        "description": {"type": "string"},
        "kind": {"enum": [k.value for k in EventKind]},
        "start_date": {"type": "string", "description": "YYYY-MM-DD"},
        "end_date": {"type": ["string", "null"], "description": "YYYY-MM-DD, multiday only"},
        "start_time": {"type": ["string", "null"], "description": "HH:MM local time, null if unknown"},
        "rrule": {"type": ["string", "null"], "description": "RFC 5545 RRULE body, recurring only"},
        "venue": _NULLABLE_STRING,
        "address": _NULLABLE_STRING,
        "price": _NULLABLE_STRING,
        "tags": {"type": "array", "items": {"type": "string"}},
        "update_kind": {"enum": [k.value for k in UpdateKind]},
        "from_organizer": {"type": "boolean"},
    },
}

_PLACE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "address", "description"],
    "properties": {"name": {"type": "string"}, "address": _NULLABLE_STRING, "description": {"type": "string"}},
}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["posts"],
    "properties": {
        "posts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["post_id", "events", "places"],
                "properties": {
                    "post_id": {"type": "integer"},
                    "events": {"type": "array", "items": _EVENT_SCHEMA},
                    "places": {"type": "array", "items": _PLACE_SCHEMA},
                },
            },
        }
    },
}

SYSTEM_PROMPT = """You turn Telegram channel posts into event cards for a person who lives in {city} and looks for things to do in person.

For every post return the events and places it announces. Most posts announce nothing: return empty lists for them.

What to keep
- Offline events that take place in {city}. Drop online events, events in other cities, ads, giveaways, news and reports about events that already happened.
- A digest post that lists many events becomes one item per event.
- A place with no date (a bar, a climbing gym, a cafe that is simply open) goes to "places", never to "events".

Fields of an event
- kind: "single" for one date; "multiday" for something that runs over a period (exhibition, festival) with start_date and end_date; "recurring" for a regular schedule ("every Tuesday at 20:00") with an RRULE body such as "FREQ=WEEKLY;BYDAY=TU" and start_date = the first occurrence on or after the post date.
- Resolve relative dates ("this Friday", "tomorrow") against the post's publication date. Without a year, pick the nearest date that is not long before the publication date.
- start_time: local time "HH:MM"; null when the post does not say. Do not guess.
- title: your own short title in {language} that says what the event is, so that a reader understands it without the description. original_title: the name as the post gives it, in the post's language.
- description: in {language}, 2–4 sentences: what happens and what it is like. Keep the author's manner and tone, do not advertise, do not repeat date, time, place or price.
- venue, address, price: as the post gives them, null if absent. price "Бесплатно"-style word in {language} when the post says it is free.
- tags: one or two from this list only: {tags}. If none fits, use exactly "{fallback}".
- update_kind: "announcement" for a normal announcement; "reschedule" when the post moves an already announced event to another date or time (give the new date and time); "cancellation" when it cancels one; "details" when it only adds details to one announced earlier.
- from_organizer: true when the channel itself organizes or hosts the event (the venue's or the organizer's own channel), false for afisha and repost channels.
"""


@dataclass(frozen=True)
class ExtractionContext:
    city: City
    language: str
    tags: list[str]
    fallback_tag: str


class PostExtractor:
    BATCH_SIZE = 8

    def __init__(self, llm: JsonLlm) -> None:
        self._llm = llm

    def batches(self, posts: list[Post]) -> list[list[Post]]:
        return [posts[i : i + self.BATCH_SIZE] for i in range(0, len(posts), self.BATCH_SIZE)]

    async def extract(
        self, posts: list[Post], sources: dict[int, Source], context: ExtractionContext
    ) -> list[PostExtraction]:
        system = SYSTEM_PROMPT.format(
            city=context.city.name,
            language=context.language,
            tags=", ".join(f'"{t}"' for t in context.tags),
            fallback=context.fallback_tag,
        )
        answer = await self._llm.complete_json(system, self._prompt(posts, sources, context.city), SCHEMA)
        by_id = {item["post_id"]: item for item in answer.get("posts", [])}
        allowed_tags = set(context.tags) | {context.fallback_tag}
        return [self._convert(post, by_id.get(post.id), allowed_tags, context.fallback_tag) for post in posts]

    @staticmethod
    def _prompt(posts: list[Post], sources: dict[int, Source], city: City) -> str:
        zone = ZoneInfo(city.timezone)
        items = [
            {
                "post_id": post.id,
                "channel": sources[post.source_id].title,
                "published": post.published_at.astimezone(zone).strftime("%Y-%m-%d %H:%M (%A)"),
                "text": post.text,
            }
            for post in posts
        ]
        return "Posts:\n" + json.dumps(items, ensure_ascii=False, indent=1)

    @classmethod
    def _convert(
        cls, post: Post, item: dict[str, Any] | None, allowed_tags: set[str], fallback: str
    ) -> PostExtraction:
        if item is None:
            return PostExtraction(post.id)
        events = tuple(e for e in (cls._event(raw, allowed_tags, fallback) for raw in item["events"]) if e)
        # Claude does not see the images. A post about one event shows that event (its first image is the
        # poster); a post about several shows them all at once, so its images belong to none of them.
        if len(events) == 1 and post.image_paths:
            events = (replace(events[0], image_index=0),)
        places = tuple(
            ExtractedPlace(p["name"], p.get("address"), p.get("description", "")) for p in item["places"]
        )
        return PostExtraction(post.id, events, places)

    @staticmethod
    def _event(raw: dict[str, Any], allowed_tags: set[str], fallback: str) -> ExtractedEvent | None:
        try:
            kind = EventKind(raw["kind"])
            start = date.fromisoformat(raw["start_date"])
            end = date.fromisoformat(raw["end_date"]) if raw.get("end_date") else None
            start_time = time.fromisoformat(raw["start_time"]) if raw.get("start_time") else None
            rrule = raw.get("rrule") or None
            if rrule:
                rrulestr(rrule, dtstart=start)
        except (ValueError, KeyError):
            return None
        if kind is EventKind.MULTIDAY and (end is None or end <= start):
            kind, end = EventKind.SINGLE, None
        if kind is EventKind.RECURRING and not rrule:
            kind = EventKind.SINGLE
        if kind is not EventKind.MULTIDAY:
            end = None
        if kind is not EventKind.RECURRING:
            rrule = None
        tags = tuple(dict.fromkeys(t for t in raw.get("tags", []) if t in allowed_tags)) or (fallback,)
        return ExtractedEvent(
            title=raw["title"].strip(),
            original_title=raw["original_title"].strip(),
            description=raw["description"].strip(),
            kind=kind,
            start_date=start,
            end_date=end,
            start_time=start_time,
            rrule=rrule,
            venue=raw.get("venue"),
            address=raw.get("address"),
            price=raw.get("price"),
            tags=tags,
            update_kind=UpdateKind(raw["update_kind"]),
            from_organizer=bool(raw["from_organizer"]),
        )
