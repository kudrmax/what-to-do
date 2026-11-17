from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, TypeAdapter

from where_to_go.feed import Feed, FeedFilter, Occurrence, PlanFilter
from where_to_go.images import ImageStore
from where_to_go.models import IMAGE_ROUTE, CityPublic, MentionPublic, SourcePublic, TagPublic
from where_to_go.originals import OriginalPosts
from where_to_go.repositories import CityRepository, MentionRepository, SettingsRepository, SourceRepository, TagRepository
from where_to_go.settings import AppSettings

Answer = dict[str, Any]


class PhoneSnapshot(BaseModel):
    """What the phone page reads instead of the API: the API's own answers for the upcoming plans of the active city."""

    made_at: datetime
    timezone: str
    settings: Answer
    cities: list[Answer]
    sources: list[Answer]
    tags: list[Answer]
    occurrences: list[Answer]
    mentions: dict[str, list[Answer]]
    images: dict[str, str]

    def content_hash(self) -> str:
        content = self.model_dump_json(exclude={"made_at"})
        return hashlib.sha256(content.encode()).hexdigest()


def _answers(model: type, values: Iterable[Any]) -> list[Answer]:
    """Values as the API serializes them under its response model."""
    adapter = TypeAdapter(list[model])
    return adapter.dump_python(adapter.validate_python(list(values), from_attributes=True), mode="json", by_alias=True)


class SnapshotBuilder:
    """The upcoming plans of the active city as the Plans screen asks the API for them, with every image file they name."""

    PLANS = frozenset({PlanFilter.MAYBE, PlanFilter.SURE})

    def __init__(
        self,
        settings: SettingsRepository,
        cities: CityRepository,
        sources: SourceRepository,
        tags: TagRepository,
        feed: Feed,
        mentions: MentionRepository,
        originals: OriginalPosts,
        images: ImageStore,
    ) -> None:
        self._settings = settings
        self._cities = cities
        self._sources = sources
        self._tags = tags
        self._feed = feed
        self._mentions = mentions
        self._originals = originals
        self._images = images

    def build(self, now: datetime) -> tuple[PhoneSnapshot, dict[str, Path]] | None:
        city = self._cities.active()
        if city is None:
            return None
        today = now.astimezone(ZoneInfo(city.timezone)).date()
        criteria = FeedFilter(start=today, plans=self.PLANS, hidden_tags=self._tags.hidden())
        occurrences = _answers(Occurrence, self._feed.occurrences(city, criteria))
        event_ids = dict.fromkeys(o["event"]["id"] for o in occurrences)
        mentions = {str(i): _answers(MentionPublic, self._originals.present(self._mentions.of_event(i))) for i in event_ids}
        urls = [o["event"]["image_url"] for o in occurrences] + [p["url"] for found in mentions.values() for m in found for p in m["photos"]]
        images, files = self._image_files(urls)
        snapshot = PhoneSnapshot(
            made_at=now,
            timezone=city.timezone,
            settings=_answers(AppSettings, [self._settings.load()])[0],
            cities=_answers(CityPublic, [city]),
            sources=_answers(SourcePublic, self._sources.in_city(city.id)),
            tags=_answers(TagPublic, self._tags.all()),
            occurrences=occurrences,
            mentions=mentions,
            images=images,
        )
        return snapshot, files

    def _image_files(self, urls: Iterable[str | None]) -> tuple[dict[str, str], dict[str, Path]]:
        """Each image URL the answers name, mapped to the encrypted file published for it; images no longer stored are left out."""
        images: dict[str, str] = {}
        files: dict[str, Path] = {}
        for url in dict.fromkeys(u for u in urls if u and u.startswith(IMAGE_ROUTE + "/")):
            path = self._images.path(url.removeprefix(IMAGE_ROUTE + "/"))
            if path is None:
                continue
            key = f"images/{path.stem}.bin"
            images[url] = key
            files[key] = path
        return images, files
