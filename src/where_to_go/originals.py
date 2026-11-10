from __future__ import annotations

import re

from where_to_go.models import IMAGE_ROUTE, Mention, MentionPublic, PostPhoto
from where_to_go.repositories import PhotoTextRepository


class EventLines:
    """Finds the lines of a post Claude quoted as being about one event.

    Claude copies lines with small differences (a link dropped, spaces changed), so lines are compared without links,
    case and extra spaces; a short quote must match a line whole, a longer one may be part of a line or contain it.
    """

    LINK = re.compile(r"\(?https?://\S+?\)?(?=\s|$)")
    PARTIAL_FROM = 12

    @classmethod
    def of(cls, text: str, quotes: list[str]) -> list[int]:
        wanted = [q for q in map(cls._normal, quotes) if q]
        if not wanted:
            return []
        found = []
        for index, line in enumerate(text.split("\n")):
            normal = cls._normal(line)
            if normal and any(cls._matches(normal, quote) for quote in wanted):
                found.append(index)
        return found

    @classmethod
    def _normal(cls, line: str) -> str:
        return " ".join(cls.LINK.sub(" ", line).lower().split())

    @classmethod
    def _matches(cls, line: str, quote: str) -> bool:
        if line == quote:
            return True
        shorter, longer = sorted((line, quote), key=len)
        return len(shorter) >= cls.PARTIAL_FROM and shorter in longer


class OriginalPosts:
    """The posts behind a card as the event window shows them: photos with what Claude read on them, and this event's lines."""

    def __init__(self, photo_texts: PhotoTextRepository) -> None:
        self._photo_texts = photo_texts

    def present(self, mentions: list[Mention]) -> list[MentionPublic]:
        texts = self._photo_texts.of(name for m in mentions for name in m.post.image_paths)
        return [self._one(m, texts) for m in self.in_order(mentions)]

    @staticmethod
    def in_order(mentions: list[Mention]) -> list[Mention]:
        """The organizer's post first, then the most detailed one, then the newest."""
        return sorted(mentions, key=lambda m: (m.data.from_organizer, len(m.data.description), m.published_at), reverse=True)

    @staticmethod
    def _one(mention: Mention, texts: dict) -> MentionPublic:
        photos = []
        for name in mention.post.image_paths:
            known = texts.get(name)
            photos.append(PostPhoto(url=f"{IMAGE_ROUTE}/{name}", text=known.text if known else None))
        public = MentionPublic.model_validate(mention, from_attributes=True)
        public.photos = photos
        public.event_photo = mention.image_index if mention.image_index is not None and mention.image_index < len(photos) else None
        public.event_lines = EventLines.of(mention.post_text, mention.data.post_lines)
        return public
