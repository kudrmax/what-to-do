"""Adding, changing and deleting cities, with what follows for the tags and the refresh."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from where_to_go.models import City, CityChange, CityContents, CityRequest
from where_to_go.repositories import CityRepository, TagRepository


class CityError(ValueError):
    pass


class DuplicateCityError(CityError):
    pass


class BusyCityError(CityError):
    pass


@dataclass(frozen=True)
class TagSet:
    names: list[str]
    fallback: str


class DefaultTags:
    """The tags a new install starts with, in the language of its first city's cards; English for any other language."""

    ENGLISH = TagSet(
        [
            "Concert",
            "Party",
            "Talk",
            "Stand-up",
            "Theatre",
            "Cinema",
            "Exhibition",
            "Games and quizzes",
            "Workshop",
            "Meetup",
            "Sports",
            "Walk",
            "Market",
            "Kids",
        ],
        "Other",
    )
    RUSSIAN = TagSet(
        [
            "Концерт",
            "Вечеринка",
            "Лекция",
            "Стендап",
            "Театр",
            "Кино",
            "Выставка",
            "Игры и квизы",
            "Мастер-класс",
            "Встреча",
            "Спорт",
            "Прогулка",
            "Маркет",
            "Детям",
        ],
        "Другое",
    )
    RUSSIAN_NAMES = frozenset({"russian", "ru", "русский", "русский язык", "по-русски"})

    @classmethod
    def for_language(cls, language: str) -> TagSet:
        return cls.RUSSIAN if language.strip().casefold() in cls.RUSSIAN_NAMES else cls.ENGLISH


class CityCatalog:
    def __init__(self, cities: CityRepository, tags: TagRepository, refreshing: Callable[[], bool]) -> None:
        self._cities = cities
        self._tags = tags
        self._refreshing = refreshing

    def add(self, request: CityRequest) -> City:
        """The first city of an install also brings the tags, in its cards' language."""
        fields = self._checked(request.model_dump())
        self._refuse_duplicate(fields["name"])
        city = self._cities.add(City(**fields))
        if not self._tags.has_fallback():
            tags = DefaultTags.for_language(city.card_language)
            self._tags.seed(tags.names, tags.fallback)
        return city

    def change(self, city_id: int, change: CityChange) -> City:
        """A new card language reads the city's recent posts again at its next refresh."""
        fields = self._checked(change.model_dump(exclude_unset=True, exclude_none=True))
        if "name" in fields:
            self._refuse_duplicate(fields["name"], city_id)
        return self._cities.change(city_id, **fields)

    def contents(self, city_id: int) -> CityContents:
        self._get(city_id)
        return self._cities.contents(city_id)

    def delete(self, city_id: int) -> None:
        self._get(city_id)
        if self._refreshing():
            raise BusyCityError("A refresh is running. Delete the city when it ends")
        self._cities.delete(city_id)

    def _get(self, city_id: int) -> City:
        city = self._cities.get(city_id)
        if city is None:
            raise KeyError(city_id)
        return city

    def _refuse_duplicate(self, name: str, city_id: int | None = None) -> None:
        same = self._cities.named(name)
        if same is not None and same.id != city_id:
            raise DuplicateCityError(f"You already have a city named “{same.name}”. Add the region to the name to tell them apart")

    @staticmethod
    def _checked(fields: dict[str, Any]) -> dict[str, Any]:
        fields = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items()}
        if "timezone" in fields:
            try:
                ZoneInfo(fields["timezone"])
            except (ZoneInfoNotFoundError, ValueError):
                raise CityError("Unknown time zone") from None
        return fields
