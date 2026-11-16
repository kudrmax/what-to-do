from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from where_to_go.llm import JsonLlm
from where_to_go.models import ChannelReference, City, EventReading, ExtractedEvent, ExtractedPlace, PhotoText, Post, Reading, Source, SourceKind
from where_to_go.photos import PhotoTranscriber
from where_to_go.reading_rules import ReadingRules


@dataclass(frozen=True)
class ExtractionContext:
    city: City
    prompt: str
    tags: list[str]
    fallback_tag: str
    priority_wish: str = ""

    @property
    def language(self) -> str:
        return self.city.card_language

    @property
    def rules(self) -> str:
        return ReadingRules.posts(self.priority_wish, self.language)

    def system(self) -> str:
        instructions = self.prompt.format(
            city=self.city.label,
            language=self.language,
            tags=", ".join(f'"{t}"' for t in self.tags),
            fallback=self.fallback_tag,
        )
        return f"{instructions}\n\n{self._priority()}"

    def _priority(self) -> str:
        if not self.priority_wish:
            return "Priority\n- Nothing is given: is_priority is always false."
        return (
            "Priority\n- What the person looks for first, in their own words:\n"
            f"<wish>\n{self.priority_wish}\n</wish>\n"
            "- Set is_priority to true for every event that clearly fits this wish, false for the rest."
        )


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

    @property
    def size(self) -> int:
        """How much Claude reads for this post: its text and the text on its photos."""
        return len(self.post.text) + sum(len(text.text) for text in self.texts.values())

    def described(self) -> list[dict[str, Any]]:
        return [{"index": index, "shows": text.shows, "text": text.text} for index, text in self.texts.items()]


class PostExtractor:
    BATCH_SIZE = 8
    BATCH_CHARS = 6000
    """Claude skips events of a call that reads too much at once, so a digest shares a call with short posts only"""

    def __init__(self, llm: JsonLlm) -> None:
        self._llm = llm

    def batches(self, posts: list[Post], photo_texts: dict[str, PhotoText]) -> list[list[Post]]:
        batches: list[list[Post]] = []
        batch: list[Post] = []
        chars = 0
        for post in posts:
            size = PostPhotos.of(post, photo_texts).size
            if batch and (len(batch) == self.BATCH_SIZE or chars + size > self.BATCH_CHARS):
                batches.append(batch)
                batch, chars = [], 0
            batch.append(post)
            chars += size
        return batches + [batch] if batch else batches

    async def extract(
        self, posts: list[Post], sources: dict[int, Source], context: ExtractionContext, photo_texts: dict[str, PhotoText]
    ) -> list[ExtractedPost]:
        system = context.system()
        photos = [PostPhotos.of(post, photo_texts) for post in posts]
        answer = await self._llm.complete_json(system, self._prompt(photos, sources, context.city), Reading.model_json_schema())
        by_id = {item.get("post_id"): item for item in answer.get("posts", []) if isinstance(item, dict)}
        allowed = set(context.tags) | {context.fallback_tag}
        return [self._convert(p, by_id.get(p.post.id, {}), allowed, context.fallback_tag, sources[p.post.source_id]) for p in photos]

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
    def _convert(cls, photos: PostPhotos, item: dict[str, Any], allowed: set[str], fallback: str, source: Source) -> ExtractedPost:
        readings = [r for r in (cls._event(raw, allowed, fallback) for raw in item.get("events", [])) if r is not None]
        places = [p for p in (cls._place(raw) for raw in item.get("places", [])) if p is not None]
        poster = cls._poster(photos.post, source)
        events = [
            (ExtractedEvent.model_validate(r.model_dump(exclude={"photo"})), r.photo if r.photo in photos.texts else poster)
            for r in readings
        ]
        channels = [c for c in (cls._channel(raw) for raw in item.get("channels", [])) if c is not None]
        return ExtractedPost(photos.post.id, events, places, channels)

    @staticmethod
    def _poster(post: Post, source: Source) -> int | None:
        """An event page's picture is that event's poster; a channel post's photo is the one Claude points to."""
        return 0 if source.kind == SourceKind.WEB and post.image_paths else None

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
