from __future__ import annotations

from collections.abc import Iterable
from itertools import groupby
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import col, select

from where_to_go.db import Database
from where_to_go.models import (
    City,
    CollectedPost,
    DevNote,
    Event,
    EventFacts,
    ExtractedEvent,
    ExtractedPlace,
    Mark,
    Mention,
    PhotoText,
    ChannelLink,
    Place,
    Post,
    PotentialSource,
    PotentialSourcePost,
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

    def to_read(self, source_ids: Iterable[int], rules: str, recent: int) -> list[Post]:
        """Posts never read, and the latest `recent` of every source read with other rules.

        A post whose events the user merged or split by hand is not read again: their decision stays.
        """
        ids = list(source_ids)
        with self._db.session() as s:
            curated = set(s.exec(select(Mention.post_id).where(Mention.locked == True)))  # noqa: E712
            chosen = {p.id: p for p in self.unprocessed(ids)}
            for source_id in ids:
                latest = s.exec(select(Post).where(Post.source_id == source_id).order_by(col(Post.published_at).desc()).limit(recent))
                chosen |= {p.id: p for p in latest if p.read_with != rules and p.id not in curated}
        return sorted(chosen.values(), key=lambda p: p.published_at)

    def get(self, post_id: int) -> Post:
        with self._db.session() as s:
            post = s.get(Post, post_id)
        if post is None:
            raise KeyError(post_id)
        return post

    def mark_processed(self, post_id: int, rules: str) -> None:
        self._change(post_id, processed_at=_now(), process_error=None, read_with=rules)

    def mark_failed(self, post_id: int, error: str) -> None:
        self._change(post_id, process_error=error)

    def _change(self, post_id: int, **fields: Any) -> None:
        with self._db.session() as s:
            post = s.get(Post, post_id)
            post.sqlmodel_update(fields)
            s.add(post)
            s.commit()


class PhotoTextRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def of(self, images: Iterable[str]) -> dict[str, PhotoText]:
        with self._db.session() as s:
            return {t.image: t for t in s.exec(select(PhotoText).where(col(PhotoText.image).in_(list(images))))}

    def save(self, texts: Iterable[PhotoText]) -> None:
        with self._db.session() as s:
            for text in texts:
                s.merge(text)
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

    def of_post(self, post_id: int) -> list[Mention]:
        with self._db.session() as s:
            return list(s.exec(select(Mention).where(Mention.post_id == post_id).order_by(Mention.item_index)).unique())

    def of_posts_with_some_photoless(self) -> list[list[Mention]]:
        """The mentions of every post where some events have a photo and some have none, post by post."""
        with self._db.session() as s:
            mixed = (
                select(Mention.post_id)
                .group_by(Mention.post_id)
                .having(func.count(Mention.image_index) > 0, func.count(Mention.image_index) < func.count())
            )
            query = select(Mention).where(col(Mention.post_id).in_(mixed)).order_by(Mention.post_id, Mention.item_index)
            mentions = list(s.exec(query).unique())
        return [list(group) for _, group in groupby(mentions, key=lambda m: m.post_id)]

    def set_image(self, mention_id: int, image_index: int) -> None:
        with self._db.session() as s:
            mention = s.get(Mention, mention_id)
            mention.image_index = image_index
            s.add(mention)
            s.commit()

    def replace(self, mention_id: int, data: ExtractedEvent, image_index: int | None) -> None:
        with self._db.session() as s:
            mention = s.get(Mention, mention_id)
            mention.data, mention.image_index = data, image_index
            s.add(mention)
            s.commit()

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

    def forget_post(self, post_id: int) -> None:
        with self._db.session() as s:
            for place in s.exec(select(Place).where(Place.post_id == post_id)).unique():
                s.delete(place)
            s.commit()

    def in_city(self, city_id: int) -> list[Place]:
        with self._db.session() as s:
            return list(s.exec(select(Place).where(Place.city_id == city_id).order_by(Place.name)).unique())


class PotentialSourceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def note(self, city_id: int, post_id: int, handles: dict[str, ChannelLink]) -> None:
        """What the post points to now replaces what it pointed to when read before.
        A processed channel takes no more posts; an unprocessed one no post points to anymore goes away."""
        with self._db.session() as s:
            for link in s.exec(select(PotentialSourcePost).where(PotentialSourcePost.post_id == post_id)).unique():
                s.delete(link)
            s.flush()
            for handle, via in handles.items():
                found = self._find(s, city_id, handle) or PotentialSource(city_id=city_id, handle=handle, found_at=_now())
                if found.processed:
                    continue
                s.add(found)
                s.flush()
                s.add(PotentialSourcePost(potential_source_id=found.id, post_id=post_id, via=via))
            s.flush()
            linked = select(PotentialSourcePost.potential_source_id)
            orphans = select(PotentialSource).where(PotentialSource.processed == False, col(PotentialSource.id).not_in(linked))  # noqa: E712
            for orphan in s.exec(orphans):
                s.delete(orphan)
            s.commit()

    def in_city(self, city_id: int) -> list[tuple[PotentialSource, list[PotentialSourcePost]]]:
        with self._db.session() as s:
            found = list(s.exec(select(PotentialSource).where(PotentialSource.city_id == city_id)))
            ids = [p.id for p in found]
            links = s.exec(select(PotentialSourcePost).where(col(PotentialSourcePost.potential_source_id).in_(ids))).unique()
            by_source: dict[int, list[PotentialSourcePost]] = {}
            for link in links:
                by_source.setdefault(link.potential_source_id, []).append(link)
            return [(p, by_source.get(p.id, [])) for p in found]

    def get(self, potential_id: int) -> PotentialSource:
        with self._db.session() as s:
            found = s.get(PotentialSource, potential_id)
        if found is None:
            raise KeyError(potential_id)
        return found

    def mark(self, potential_id: int, processed: bool) -> PotentialSource:
        with self._db.session() as s:
            found = s.get(PotentialSource, potential_id)
            if found is None:
                raise KeyError(potential_id)
            found.processed = processed
            s.add(found)
            s.commit()
            s.refresh(found)
            return found

    @staticmethod
    def _find(s: Any, city_id: int, handle: str) -> PotentialSource | None:
        query = select(PotentialSource).where(PotentialSource.city_id == city_id, func.lower(PotentialSource.handle) == handle.lower())
        return s.exec(query).first()


class EventRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create(self, city_id: int, facts: EventFacts) -> Event:
        return self.save(Event(city_id=city_id, **facts.facts()))

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


class DevNoteRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, event_id: int, text: str) -> DevNote:
        note = DevNote(event_id=event_id, text=text, created_at=_now())
        with self._db.session() as session:
            session.add(note)
            session.commit()
            session.refresh(note)
        return note
