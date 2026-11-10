from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from where_to_go.llm import JsonLlm
from where_to_go.models import ChannelReference, City, EventReading, ExtractedEvent, ExtractedPlace, PhotoText, Post, Reading, Source
from where_to_go.photos import PhotoTranscriber
from where_to_go.reading_rules import ReadingRules


@dataclass(frozen=True)
class ExtractionContext:
    city: City
    prompt: str
    language: str
    tags: list[str]
    fallback_tag: str

    @property
    def rules(self) -> str:
        return ReadingRules.POSTS


@dataclass(frozen=True)
class ExtractedPost:
    """What one post announces, with the index of the post image each event gets."""

    post_id: int
    events: list[tuple[ExtractedEvent, int | None]] = field(default_factory=list)
    places: list[ExtractedPlace] = field(default_factory=list)
    channels: list[ChannelReference] = field(default_factory=list)


@dataclass(frozen=True)
class PostPhotos:
    """The transcribed photos of one post, by their index among the post's images."""

    post: Post
    texts: dict[int, PhotoText]

    @classmethod
    def of(cls, post: Post, texts: dict[str, PhotoText]) -> PostPhotos:
        shown = enumerate(PhotoTranscriber.shown(post))
        return cls(post, {index: texts[name] for index, name in shown if name in texts})

    def described(self) -> list[dict[str, Any]]:
        return [{"index": index, "shows": text.shows, "text": text.text} for index, text in self.texts.items()]


class PostExtractor:
    BATCH_SIZE = 8

    def __init__(self, llm: JsonLlm) -> None:
        self._llm = llm

    def batches(self, posts: list[Post]) -> list[list[Post]]:
        return [posts[i : i + self.BATCH_SIZE] for i in range(0, len(posts), self.BATCH_SIZE)]

    async def extract(
        self, posts: list[Post], sources: dict[int, Source], context: ExtractionContext, photo_texts: dict[str, PhotoText]
    ) -> list[ExtractedPost]:
        system = context.prompt.format(
            city=context.city.name,
            language=context.language,
            tags=", ".join(f'"{t}"' for t in context.tags),
            fallback=context.fallback_tag,
        )
        photos = [PostPhotos.of(post, photo_texts) for post in posts]
        answer = await self._llm.complete_json(system, self._prompt(photos, sources, context.city), Reading.model_json_schema())
        by_id = {item.get("post_id"): item for item in answer.get("posts", []) if isinstance(item, dict)}
        allowed = set(context.tags) | {context.fallback_tag}
        return [self._convert(p, by_id.get(p.post.id, {}), allowed, context.fallback_tag) for p in photos]

    @staticmethod
    def _prompt(photos: list[PostPhotos], sources: dict[int, Source], city: City) -> str:
        zone = ZoneInfo(city.timezone)
        items = [
            {
                "post_id": p.post.id,
                "channel": sources[p.post.source_id].title,
                "published": p.post.published_at.astimezone(zone).strftime("%Y-%m-%d %H:%M (%A)"),
                "text": p.post.text,
                "photos": p.described(),
            }
            for p in photos
        ]
        return "Posts:\n" + json.dumps(items, ensure_ascii=False, indent=1)

    @classmethod
    def _convert(cls, photos: PostPhotos, item: dict[str, Any], allowed: set[str], fallback: str) -> ExtractedPost:
        readings = [r for r in (cls._event(raw, allowed, fallback) for raw in item.get("events", [])) if r is not None]
        places = [p for p in (cls._place(raw) for raw in item.get("places", [])) if p is not None]
        events = [
            (ExtractedEvent.model_validate(r.model_dump(exclude={"photo"})), r.photo if r.photo in photos.texts else None)
            for r in readings
        ]
        channels = [c for c in (cls._channel(raw) for raw in item.get("channels", [])) if c is not None]
        return ExtractedPost(photos.post.id, events, places, channels)

    @staticmethod
    def _event(raw: Any, allowed: set[str], fallback: str) -> EventReading | None:
        """An item Claude got wrong is dropped, not the whole post."""
        try:
            event = EventReading.model_validate(raw)
        except ValidationError:
            return None
        event.tags = list(dict.fromkeys(t for t in event.tags if t in allowed)) or [fallback]
        return event

    @staticmethod
    def _place(raw: Any) -> ExtractedPlace | None:
        try:
            return ExtractedPlace.model_validate(raw)
        except ValidationError:
            return None

    @staticmethod
    def _channel(raw: Any) -> ChannelReference | None:
        try:
            return ChannelReference.model_validate(raw)
        except ValidationError:
            return None
