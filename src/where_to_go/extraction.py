from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from where_to_go.llm import JsonLlm
from where_to_go.models import City, ExtractedEvent, ExtractedPlace, Post, Reading, Source

@dataclass(frozen=True)
class ExtractionContext:
    city: City
    prompt: str
    language: str
    tags: list[str]
    fallback_tag: str


@dataclass(frozen=True)
class ExtractedPost:
    """What one post announces, with the image each event gets."""

    post_id: int
    events: list[tuple[ExtractedEvent, int | None]] = field(default_factory=list)
    places: list[ExtractedPlace] = field(default_factory=list)


class PostExtractor:
    BATCH_SIZE = 8

    def __init__(self, llm: JsonLlm) -> None:
        self._llm = llm

    def batches(self, posts: list[Post]) -> list[list[Post]]:
        return [posts[i : i + self.BATCH_SIZE] for i in range(0, len(posts), self.BATCH_SIZE)]

    async def extract(self, posts: list[Post], sources: dict[int, Source], context: ExtractionContext) -> list[ExtractedPost]:
        system = context.prompt.format(
            city=context.city.name,
            language=context.language,
            tags=", ".join(f'"{t}"' for t in context.tags),
            fallback=context.fallback_tag,
        )
        answer = await self._llm.complete_json(system, self._prompt(posts, sources, context.city), Reading.model_json_schema())
        by_id = {item.get("post_id"): item for item in answer.get("posts", []) if isinstance(item, dict)}
        allowed = set(context.tags) | {context.fallback_tag}
        return [self._convert(post, by_id.get(post.id, {}), allowed, context.fallback_tag) for post in posts]

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
    def _convert(cls, post: Post, item: dict[str, Any], allowed: set[str], fallback: str) -> ExtractedPost:
        events = [e for e in (cls._event(raw, allowed, fallback) for raw in item.get("events", [])) if e is not None]
        places = [p for p in (cls._place(raw) for raw in item.get("places", [])) if p is not None]
        # Claude does not see the images. A post about one event shows that event (its first image is the
        # poster); a post about several shows them all at once, so its images belong to none of them.
        image = 0 if len(events) == 1 and post.image_paths else None
        return ExtractedPost(post.id, [(event, image) for event in events], places)

    @staticmethod
    def _event(raw: Any, allowed: set[str], fallback: str) -> ExtractedEvent | None:
        """An item Claude got wrong is dropped, not the whole post."""
        try:
            event = ExtractedEvent.model_validate(raw)
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

