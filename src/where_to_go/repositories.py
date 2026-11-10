from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_
from sqlmodel import col, select

from where_to_go.db import Database
from where_to_go.models import (
    City,
    CollectedPost,
    Event,
    EventFacts,
    ExtractedEvent,
    ExtractedPlace,
    Mark,
    Mention,
    Place,
    Post,
    Setting,
    Source,
    Tag,
)
from where_to_go.settings import AppSettings


def _now() -> datetime:
    return datetime.now(UTC)


class SettingsRepository:
    """Stores AppSettings field by field, so a new setting needs no storage code."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load(self) -> AppSettings:
        with self._db.session() as s:
            return AppSettings.model_validate({row.key: row.value for row in s.exec(select(Setting))})

    def update(self, **change: Any) -> AppSettings:
        updated = AppSettings.model_validate({**self.load().model_dump(), **change})
        with self._db.session() as s:
            for key in change:
                s.merge(Setting(key=key, value=updated.model_dump(mode="json")[key]))
            s.commit()
        return updated


class CityRepository:
    def __init__(self, db: Database, settings: SettingsRepository) -> None:
        self._db = db
        self._settings = settings

    def add(self, name: str, timezone: str) -> City:
        """The first city a user adds becomes the active one."""
        city = self._save(City(name=name, timezone=timezone))
        if self._settings.load().active_city_id is None:
            self._settings.update(active_city_id=city.id)
        return city

    def get(self, city_id: int) -> City | None:
        with self._db.session() as s:
            return s.get(City, city_id)

    def active(self) -> City | None:
        city_id = self._settings.load().active_city_id
        return self.get(city_id) if city_id else None

    def all(self) -> list[City]:
        with self._db.session() as s:
            return list(s.exec(select(City).order_by(City.name)))

    def _save(self, city: City) -> City:
        with self._db.session() as s:
            s.add(city)
            s.commit()
            s.refresh(city)
            return city


class SourceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, source: Source) -> Source:
        with self._db.session() as s:
            s.add(source)
            s.commit()
            s.refresh(source)
            return source

    def get(self, source_id: int) -> Source:
        with self._db.session() as s:
            source = s.get(Source, source_id)
        if source is None:
            raise KeyError(source_id)
        return source

    def in_city(self, city_id: int) -> list[Source]:
        with self._db.session() as s:
            return list(s.exec(select(Source).where(Source.city_id == city_id).order_by(Source.title)))

    def change(self, source_id: int, **fields: Any) -> Source:
        with self._db.session() as s:
            source = s.get(Source, source_id)
            if source is None:
                raise KeyError(source_id)
            source.sqlmodel_update(fields)
            s.add(source)
            s.commit()
            s.refresh(source)
            return source

    def delete(self, source_id: int) -> None:
        with self._db.session() as s:
            source = s.get(Source, source_id)
            if source is not None:
                s.delete(source)
                s.commit()

    def record_success(self, source_id: int) -> None:
        self.change(source_id, last_refreshed_at=_now(), last_error=None)

    def record_error(self, source_id: int, error: str) -> None:
        self.change(source_id, last_refreshed_at=_now(), last_error=error)

    def recount_events(self, events: EventRepository) -> None:
        with self._db.session() as s:
            for source in s.exec(select(Source)):
                source.events_found = len(events.ids_of_source(source.id))
                s.add(source)
            s.commit()


class PostRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add_new(self, source_id: int, post: CollectedPost, image_paths: list[str]) -> bool:
        with self._db.session() as s:
            if s.exec(select(Post.id).where(Post.source_id == source_id, Post.external_id == post.external_id)).first():
                return False
            fields = post.model_dump(exclude={"image_urls"})
            s.add(Post(source_id=source_id, image_paths=image_paths, **fields))
            s.commit()
            return True

    def known_ids(self, source_id: int) -> set[int]:
        with self._db.session() as s:
            return set(s.exec(select(Post.external_id).where(Post.source_id == source_id)))

    def unprocessed(self, source_ids: Iterable[int]) -> list[Post]:
        with self._db.session() as s:
            query = select(Post).where(col(Post.processed_at).is_(None), col(Post.source_id).in_(list(source_ids)))
            return list(s.exec(query.order_by(Post.published_at)))

    def get(self, post_id: int) -> Post:
        with self._db.session() as s:
            post = s.get(Post, post_id)
        if post is None:
            raise KeyError(post_id)
        return post

    def mark_processed(self, post_id: int) -> None:
        self._change(post_id, processed_at=_now(), process_error=None)

    def mark_failed(self, post_id: int, error: str) -> None:
        self._change(post_id, process_error=error)

    def _change(self, post_id: int, **fields: Any) -> None:
        with self._db.session() as s:
            post = s.get(Post, post_id)
            post.sqlmodel_update(fields)
            s.add(post)
            s.commit()


class TagRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def all(self) -> list[Tag]:
        with self._db.session() as s:
            return list(s.exec(select(Tag).order_by(Tag.is_fallback, Tag.position)))

    def fallback(self) -> str:
        return next(t.name for t in self.all() if t.is_fallback)

    def ensure_seeded(self, names: list[str], fallback: str) -> None:
        with self._db.session() as s:
            if s.exec(select(Tag.id)).first():
                return
            s.add_all(Tag(name=name, position=i) for i, name in enumerate(names))
            s.add(Tag(name=fallback, position=len(names), is_fallback=True))
            s.commit()

    def add(self, name: str) -> Tag:
        with self._db.session() as s:
            position = max((t.position for t in s.exec(select(Tag).where(Tag.is_fallback == False))), default=-1) + 1  # noqa: E712
            tag = Tag(name=name, position=position)
            s.add(tag)
            s.commit()
            s.refresh(tag)
            return tag

    def rename(self, tag_id: int, name: str) -> Tag:
        """Renames a tag on every card too. The fallback tag keeps its name: Claude and the cards rely on it."""
        with self._db.session() as s:
            tag = s.get(Tag, tag_id)
            if tag is None:
                raise KeyError(tag_id)
            if tag.is_fallback:
                raise ValueError(f"Тег «{tag.name}» переименовать нельзя")
            old, tag.name = tag.name, name
            s.add(tag)
            for event in s.exec(select(Event)):
                if old in event.tags:
                    event.tags = [name if t == old else t for t in event.tags]
                    s.add(event)
            s.commit()
            s.refresh(tag)
            return tag


class MentionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, post_id: int, item_index: int, data: ExtractedEvent, image_index: int | None) -> Mention:
        with self._db.session() as s:
            mention = Mention(post_id=post_id, item_index=item_index, data=data, image_index=image_index)
            s.add(mention)
            s.commit()
            s.refresh(mention)
            return mention

    def get(self, mention_id: int) -> Mention:
        with self._db.session() as s:
            mention = s.get(Mention, mention_id)
        if mention is None:
            raise KeyError(mention_id)
        return mention

    def unassigned(self, source_ids: Iterable[int]) -> list[Mention]:
        with self._db.session() as s:
            query = (
                select(Mention)
                .join(Post)
                .where(col(Mention.event_id).is_(None), col(Post.source_id).in_(list(source_ids)))
                .order_by(Post.published_at, Mention.item_index)
            )
            return list(s.exec(query).unique())

    def delete(self, mention_id: int) -> None:
        with self._db.session() as s:
            s.delete(s.get(Mention, mention_id))
            s.commit()

    def of_event(self, event_id: int) -> list[Mention]:
        with self._db.session() as s:
            query = select(Mention).join(Post).where(Mention.event_id == event_id).order_by(Post.published_at)
            return list(s.exec(query).unique())

    def assign(self, mention_id: int, event_id: int, locked: bool = False) -> None:
        with self._db.session() as s:
            mention = s.get(Mention, mention_id)
            mention.event_id = event_id
            mention.locked = mention.locked or locked
            s.add(mention)
            s.commit()


class PlaceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, city_id: int, post_id: int, place: ExtractedPlace) -> None:
        with self._db.session() as s:
            s.add(Place(city_id=city_id, post_id=post_id, **place.model_dump()))
            s.commit()

    def in_city(self, city_id: int) -> list[Place]:
        with self._db.session() as s:
            return list(s.exec(select(Place).where(Place.city_id == city_id).order_by(Place.name)).unique())


class EventRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, city_id: int, facts: EventFacts) -> Event:
        return self.save(Event(city_id=city_id, **facts.model_dump(include=set(EventFacts.model_fields))))

    def save(self, event: Event) -> Event:
        with self._db.session() as s:
            event = s.merge(event)
            s.commit()
            s.refresh(event)
            return event

    def get(self, event_id: int) -> Event:
        with self._db.session() as s:
            event = s.get(Event, event_id)
        if event is None:
            raise KeyError(event_id)
        return event

    def in_city(self, city_id: int) -> list[Event]:
        with self._db.session() as s:
            return list(s.exec(select(Event).where(Event.city_id == city_id).order_by(Event.start_date, Event.start_time)))

    def near(self, city_id: int, start: date, end: date) -> list[Event]:
        """Events that may overlap [start, end]; recurring ones are always included."""
        with self._db.session() as s:
            ends = col(Event.end_date)
            query = select(Event).where(
                Event.city_id == city_id,
                or_(
                    col(Event.rrule).is_not(None),
                    (col(Event.start_date) <= end) & (or_(ends >= start, ends.is_(None) & (col(Event.start_date) >= start))),
                ),
            )
            return list(s.exec(query))

    def ids_of_source(self, source_id: int) -> set[int]:
        with self._db.session() as s:
            return {event.id for event in s.exec(select(Event)) if source_id in event.source_ids}

    def delete(self, event_id: int) -> None:
        with self._db.session() as s:
            event = s.get(Event, event_id)
            if event is not None:
                s.delete(event)
                s.commit()

    def set_mark(self, event_id: int, mark: Mark) -> Event:
        event = self.get(event_id)
        event.sqlmodel_update(mark.model_dump(include=set(Mark.model_fields)))
        event.marked_at = _now()
        return self.save(event)
