from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from where_to_go.feed import Feed, FeedFilter, PlanFilter
from where_to_go.images import ImageStore
from where_to_go.repositories import CityRepository, MentionRepository, TagRepository


class PhoneOccurrence(BaseModel):
    date: date
    event: dict[str, Any]
    post_url: str | None


class PhoneSnapshot(BaseModel):
    made_at: datetime
    city: str
    timezone: str
    today: date
    tags: list[str]
    occurrences: list[PhoneOccurrence]

    def content_hash(self) -> str:
        content = self.model_dump_json(exclude={"made_at"})
        return hashlib.sha256(content.encode()).hexdigest()


class SnapshotBuilder:
    """The upcoming plans of the active city, as the Plans screen lists them, with the poster files they need."""

    PLANS = frozenset({PlanFilter.MAYBE, PlanFilter.SURE})

    def __init__(self, feed: Feed, cities: CityRepository, tags: TagRepository, mentions: MentionRepository, images: ImageStore) -> None:
        self._feed = feed
        self._cities = cities
        self._tags = tags
        self._mentions = mentions
        self._images = images

    def build(self, now: datetime) -> tuple[PhoneSnapshot, dict[str, Path]] | None:
        city = self._cities.active()
        if city is None:
            return None
        today = now.astimezone(ZoneInfo(city.timezone)).date()
        criteria = FeedFilter(start=today, plans=self.PLANS, hidden_tags=self._tags.hidden())
        files: dict[str, Path] = {}
        occurrences = []
        for occurrence in self._feed.occurrences(city, criteria):
            event = occurrence.event
            data = event.model_dump(mode="json")
            data["image_url"] = self._poster(event.image_path, files)
            mentions = self._mentions.of_event(event.id)
            occurrences.append(PhoneOccurrence(date=occurrence.date, event=data, post_url=mentions[-1].post_url if mentions else None))
        snapshot = PhoneSnapshot(
            made_at=now,
            city=city.label,
            timezone=city.timezone,
            today=today,
            tags=[tag.name for tag in self._tags.all()],
            occurrences=occurrences,
        )
        return snapshot, files

    def _poster(self, image_path: str | None, files: dict[str, Path]) -> str | None:
        path = self._images.path(image_path) if image_path else None
        if path is None:
            return None
        key = f"images/{path.stem}.bin"
        files[key] = path
        return key
