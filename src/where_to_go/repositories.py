from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import UTC, date, datetime, time
from typing import Any

from where_to_go.db import Database
from where_to_go.settings import AppSettings
from where_to_go.domain import (
    City,
    CollectedPost,
    Conflict,
    Event,
    EventKind,
    ExtractedEvent,
    ExtractedPlace,
    Mark,
    Mention,
    Plan,
    Post,
    Source,
    SourceKind,
    Tag,
    UpdateKind,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _opt_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _opt_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


class ExtractedEventCodec:
    @staticmethod
    def dump(event: ExtractedEvent) -> str:
        raw = asdict(event)
        raw["start_date"] = event.start_date.isoformat()
        raw["end_date"] = event.end_date.isoformat() if event.end_date else None
        raw["start_time"] = event.start_time.strftime("%H:%M") if event.start_time else None
        raw["tags"] = list(event.tags)
        return json.dumps(raw, ensure_ascii=False)

    @staticmethod
    def load(text: str) -> ExtractedEvent:
        raw = json.loads(text)
        return ExtractedEvent(
            title=raw["title"],
            original_title=raw["original_title"],
            description=raw["description"],
            kind=EventKind(raw["kind"]),
            start_date=date.fromisoformat(raw["start_date"]),
            end_date=_opt_date(raw.get("end_date")),
            start_time=_opt_time(raw.get("start_time")),
            rrule=raw.get("rrule"),
            venue=raw.get("venue"),
            address=raw.get("address"),
            price=raw.get("price"),
            tags=tuple(raw.get("tags", ())),
            update_kind=UpdateKind(raw.get("update_kind", UpdateKind.ANNOUNCEMENT)),
            from_organizer=bool(raw.get("from_organizer")),
            image_index=raw.get("image_index"),
        )


class SettingsRepository:
    """Stores AppSettings field by field, so a new setting needs no storage code."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def load(self) -> AppSettings:
        stored = {row["key"]: json.loads(row["value"]) for row in self._db.query("SELECT key, value FROM settings")}
        return AppSettings.model_validate(stored)

    def update(self, **change: Any) -> AppSettings:
        updated = AppSettings.model_validate({**self.load().model_dump(), **change})
        with self._db.transaction() as conn:
            for key in change:
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(getattr(updated, key), ensure_ascii=False)),
                )
        return updated


class CityRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, name: str, timezone: str) -> City:
        city_id = self._db.execute("INSERT INTO cities (name, timezone) VALUES (?, ?)", (name, timezone))
        return City(city_id, name, timezone)

    def get(self, city_id: int) -> City | None:
        row = self._db.query_one("SELECT * FROM cities WHERE id = ?", (city_id,))
        return City(row["id"], row["name"], row["timezone"]) if row else None

    def all(self) -> list[City]:
        return [City(r["id"], r["name"], r["timezone"]) for r in self._db.query("SELECT * FROM cities ORDER BY name")]


class SourceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _row(row: sqlite3.Row) -> Source:
        return Source(
            id=row["id"],
            city_id=row["city_id"],
            kind=SourceKind(row["kind"]),
            handle=row["handle"],
            title=row["title"],
            last_refreshed_at=datetime.fromisoformat(row["last_refreshed_at"]) if row["last_refreshed_at"] else None,
            last_error=row["last_error"],
            last_post_id=row["last_post_id"],
            events_found=row["events_found"],
        )

    def add(self, city_id: int, kind: SourceKind, handle: str, title: str) -> Source:
        source_id = self._db.execute(
            "INSERT INTO sources (city_id, kind, handle, title) VALUES (?, ?, ?, ?)",
            (city_id, kind.value, handle, title),
        )
        return self.get(source_id)

    def get(self, source_id: int) -> Source:
        row = self._db.query_one("SELECT * FROM sources WHERE id = ?", (source_id,))
        if row is None:
            raise KeyError(source_id)
        return self._row(row)

    def in_city(self, city_id: int) -> list[Source]:
        rows = self._db.query("SELECT * FROM sources WHERE city_id = ? ORDER BY title", (city_id,))
        return [self._row(r) for r in rows]

    def rename(self, source_id: int, title: str) -> None:
        self._db.execute("UPDATE sources SET title = ? WHERE id = ?", (title, source_id))

    def delete(self, source_id: int) -> None:
        self._db.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    def record_success(self, source_id: int, last_post_id: int | None) -> None:
        self._db.execute(
            "UPDATE sources SET last_refreshed_at = ?, last_error = NULL, "
            "last_post_id = NULLIF(MAX(COALESCE(?, 0), COALESCE(last_post_id, 0)), 0) WHERE id = ?",
            (_now(), last_post_id, source_id),
        )

    def record_error(self, source_id: int, error: str) -> None:
        self._db.execute(
            "UPDATE sources SET last_refreshed_at = ?, last_error = ? WHERE id = ?",
            (_now(), error, source_id),
        )

    def recount_events(self) -> None:
        self._db.execute(
            "UPDATE sources SET events_found = ("
            " SELECT COUNT(DISTINCT m.event_id) FROM mentions m JOIN posts p ON p.id = m.post_id"
            " WHERE p.source_id = sources.id AND m.event_id IS NOT NULL)"
        )


class PostRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _row(row: sqlite3.Row) -> Post:
        return Post(
            id=row["id"],
            source_id=row["source_id"],
            external_id=row["external_id"],
            url=row["url"],
            published_at=datetime.fromisoformat(row["published_at"]),
            text=row["text"],
            image_paths=tuple(json.loads(row["image_paths"])),
        )

    def add_new(self, source_id: int, post: CollectedPost, image_paths: list[str]) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO posts (source_id, external_id, url, published_at, text, image_paths) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    source_id,
                    post.external_id,
                    post.url,
                    post.published_at.isoformat(),
                    post.text,
                    json.dumps(image_paths),
                ),
            )
            return cursor.rowcount > 0

    def known_ids(self, source_id: int) -> set[int]:
        rows = self._db.query("SELECT external_id FROM posts WHERE source_id = ?", (source_id,))
        return {r["external_id"] for r in rows}

    def unprocessed(self, source_ids: list[int]) -> list[Post]:
        if not source_ids:
            return []
        marks = ",".join("?" * len(source_ids))
        rows = self._db.query(
            f"SELECT * FROM posts WHERE processed_at IS NULL AND source_id IN ({marks}) ORDER BY published_at",
            tuple(source_ids),
        )
        return [self._row(r) for r in rows]

    def get(self, post_id: int) -> Post:
        row = self._db.query_one("SELECT * FROM posts WHERE id = ?", (post_id,))
        if row is None:
            raise KeyError(post_id)
        return self._row(row)

    def mark_processed(self, post_id: int) -> None:
        self._db.execute(
            "UPDATE posts SET processed_at = ?, process_error = NULL WHERE id = ?", (_now(), post_id)
        )

    def mark_failed(self, post_id: int, error: str) -> None:
        self._db.execute("UPDATE posts SET process_error = ? WHERE id = ?", (error, post_id))


class TagRepository:
    FALLBACK = "не распознано"

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _row(row: sqlite3.Row) -> Tag:
        return Tag(row["id"], row["name"], row["position"], bool(row["is_fallback"]))

    def all(self) -> list[Tag]:
        return [self._row(r) for r in self._db.query("SELECT * FROM tags ORDER BY is_fallback, position")]

    def ensure_seeded(self, names: list[str]) -> None:
        if self._db.query_one("SELECT 1 FROM tags"):
            return
        with self._db.transaction() as conn:
            for position, name in enumerate(names):
                conn.execute("INSERT INTO tags (name, position) VALUES (?, ?)", (name, position))
            conn.execute(
                "INSERT INTO tags (name, position, is_fallback) VALUES (?, ?, 1)", (self.FALLBACK, len(names))
            )

    def add(self, name: str) -> Tag:
        row = self._db.query_one("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM tags WHERE is_fallback = 0")
        tag_id = self._db.execute("INSERT INTO tags (name, position) VALUES (?, ?)", (name, row["p"]))
        return Tag(tag_id, name, row["p"])

    def rename(self, tag_id: int, name: str) -> None:
        with self._db.transaction() as conn:
            old = conn.execute("SELECT name FROM tags WHERE id = ?", (tag_id,)).fetchone()
            if old is None:
                raise KeyError(tag_id)
            conn.execute("UPDATE tags SET name = ? WHERE id = ?", (name, tag_id))
            for row in conn.execute("SELECT id, tags FROM events").fetchall():
                tags = [name if t == old["name"] else t for t in json.loads(row["tags"])]
                conn.execute("UPDATE events SET tags = ? WHERE id = ?", (json.dumps(tags, ensure_ascii=False), row["id"]))


class MentionRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    _SELECT = (
        "SELECT m.*, p.published_at, p.source_id, p.image_paths FROM mentions m JOIN posts p ON p.id = m.post_id "
    )

    @staticmethod
    def _row(row: sqlite3.Row) -> Mention:
        data = ExtractedEventCodec.load(row["data"])
        images = json.loads(row["image_paths"])
        index = data.image_index
        return Mention(
            id=row["id"],
            post_id=row["post_id"],
            event_id=row["event_id"],
            item_index=row["item_index"],
            data=data,
            published_at=datetime.fromisoformat(row["published_at"]),
            source_id=row["source_id"],
            image_path=images[index] if index is not None and 0 <= index < len(images) else None,
            locked=bool(row["locked"]),
        )

    def add(self, post_id: int, item_index: int, data: ExtractedEvent) -> int:
        return self._db.execute(
            "INSERT INTO mentions (post_id, item_index, data) VALUES (?, ?, ?)",
            (post_id, item_index, ExtractedEventCodec.dump(data)),
        )

    def get(self, mention_id: int) -> Mention:
        row = self._db.query_one(self._SELECT + "WHERE m.id = ?", (mention_id,))
        if row is None:
            raise KeyError(mention_id)
        return self._row(row)

    def unassigned(self) -> list[Mention]:
        rows = self._db.query(self._SELECT + "WHERE m.event_id IS NULL ORDER BY p.published_at, m.item_index")
        return [self._row(r) for r in rows]

    def of_event(self, event_id: int) -> list[Mention]:
        rows = self._db.query(self._SELECT + "WHERE m.event_id = ? ORDER BY p.published_at", (event_id,))
        return [self._row(r) for r in rows]

    def assign(self, mention_id: int, event_id: int, locked: bool = False) -> None:
        self._db.execute(
            "UPDATE mentions SET event_id = ?, locked = MAX(locked, ?) WHERE id = ?",
            (event_id, int(locked), mention_id),
        )


class PlaceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add(self, city_id: int, post_id: int, place: ExtractedPlace) -> None:
        self._db.execute(
            "INSERT INTO places (city_id, post_id, name, address, description) VALUES (?, ?, ?, ?, ?)",
            (city_id, post_id, place.name, place.address, place.description),
        )

    def in_city(self, city_id: int) -> list[dict]:
        rows = self._db.query(
            "SELECT pl.*, p.url AS post_url FROM places pl JOIN posts p ON p.id = pl.post_id "
            "WHERE pl.city_id = ? ORDER BY pl.name",
            (city_id,),
        )
        return [dict(r) for r in rows]


class EventRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    _SELECT = (
        "SELECT e.*, k.interest, k.plan, "
        "(SELECT json_group_array(DISTINCT p.source_id) FROM mentions m JOIN posts p ON p.id = m.post_id "
        " WHERE m.event_id = e.id) AS source_ids "
        "FROM events e LEFT JOIN marks k ON k.event_id = e.id "
    )

    @staticmethod
    def _row(row: sqlite3.Row) -> Event:
        return Event(
            id=row["id"],
            city_id=row["city_id"],
            kind=EventKind(row["kind"]),
            title=row["title"],
            original_title=row["original_title"],
            description=row["description"],
            start_date=date.fromisoformat(row["start_date"]),
            end_date=_opt_date(row["end_date"]),
            start_time=_opt_time(row["start_time"]),
            rrule=row["rrule"],
            venue=row["venue"],
            address=row["address"],
            price=row["price"],
            tags=tuple(json.loads(row["tags"])),
            image_path=row["image_path"],
            is_cancelled=bool(row["is_cancelled"]),
            conflicts=tuple(Conflict(c["field"], tuple(c["values"])) for c in json.loads(row["conflicts"])),
            source_ids=tuple(sorted(json.loads(row["source_ids"] or "[]"))),
            mark=Mark(row["interest"], Plan(row["plan"]) if row["plan"] else None),
        )

    def create(self, city_id: int, seed: ExtractedEvent) -> int:
        return self._db.execute(
            "INSERT INTO events (city_id, kind, title, original_title, description, start_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (city_id, seed.kind.value, seed.title, seed.original_title, seed.description, seed.start_date.isoformat()),
        )

    def get(self, event_id: int) -> Event:
        row = self._db.query_one(self._SELECT + "WHERE e.id = ?", (event_id,))
        if row is None:
            raise KeyError(event_id)
        return self._row(row)

    def save_resolved(self, event: Event) -> None:
        self._db.execute(
            "UPDATE events SET kind = ?, title = ?, original_title = ?, description = ?, start_date = ?, "
            "end_date = ?, start_time = ?, rrule = ?, venue = ?, address = ?, price = ?, tags = ?, "
            "image_path = ?, is_cancelled = ?, conflicts = ? WHERE id = ?",
            (
                event.kind.value,
                event.title,
                event.original_title,
                event.description,
                event.start_date.isoformat(),
                event.end_date.isoformat() if event.end_date else None,
                event.start_time.strftime("%H:%M") if event.start_time else None,
                event.rrule,
                event.venue,
                event.address,
                event.price,
                json.dumps(list(event.tags), ensure_ascii=False),
                event.image_path,
                int(event.is_cancelled),
                json.dumps([{"field": c.field, "values": list(c.values)} for c in event.conflicts], ensure_ascii=False),
                event.id,
            ),
        )

    def in_city(self, city_id: int) -> list[Event]:
        rows = self._db.query(self._SELECT + "WHERE e.city_id = ? ORDER BY e.start_date, e.start_time", (city_id,))
        return [self._row(r) for r in rows]

    def near(self, city_id: int, start: date, end: date) -> list[Event]:
        """Events that may overlap [start, end]; recurring ones are always included."""
        rows = self._db.query(
            self._SELECT + "WHERE e.city_id = ? AND (e.rrule IS NOT NULL OR "
            "(e.start_date <= ? AND COALESCE(e.end_date, e.start_date) >= ?))",
            (city_id, end.isoformat(), start.isoformat()),
        )
        return [self._row(r) for r in rows]

    def delete(self, event_id: int) -> None:
        self._db.execute("DELETE FROM events WHERE id = ?", (event_id,))

    def set_mark(self, event_id: int, mark: Mark) -> None:
        self._db.execute(
            "INSERT INTO marks (event_id, interest, plan, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(event_id) DO UPDATE SET interest = excluded.interest, plan = excluded.plan, "
            "updated_at = excluded.updated_at",
            (event_id, mark.interest, mark.plan.value if mark.plan else None, _now()),
        )
