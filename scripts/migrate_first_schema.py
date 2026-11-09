"""Moves a data folder of the first version (hand-written tables, prices as text) to the current models.

Posts, mentions, manual merges and splits, marks, sources, tags and settings are kept; cards are rebuilt from
their mentions. Text prices become numbers: «Бесплатно» is 0, «1000 RSD по регистрации, без неё 1500 RSD»
is 1000 RSD, a donation of any size has no price. No Claude calls.

Usage: migrate_first_schema.py <old data dir> <new data dir>
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from sqlmodel import select

from where_to_go.container import Container
from where_to_go.models import City, Event, ExtractedEvent, Mention, Place, Plan, Post, Setting, Source, Tag

FREE = re.compile(r"бесплат|free|вход свободный|gratis|besplatn", re.IGNORECASE)
DONATION = re.compile(r"donat|донат|по желанию|сколько не жалко", re.IGNORECASE)
NUMBER = re.compile(r"\d[\d\s.,]*")
CURRENCIES = {"RSD": re.compile(r"rsd|дин|din", re.IGNORECASE), "EUR": re.compile(r"eur|€|евро", re.IGNORECASE)}


class TextPrice:
    @staticmethod
    def parse(text: str | None) -> tuple[float | None, str | None]:
        if not text:
            return None, None
        amounts = [float(re.sub(r"[\s.,]", "", n)) for n in NUMBER.findall(text) if re.sub(r"[\s.,]", "", n)]
        if amounts:
            currency = next((code for code, pattern in CURRENCIES.items() if pattern.search(text)), None)
            return min(amounts), currency
        if FREE.search(text) and not DONATION.search(text):
            return 0.0, None
        return None, None


def rows(old: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return old.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608 (fixed table names)


def stamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def mention_data(raw: dict) -> tuple[ExtractedEvent, int | None]:
    price, currency = TextPrice.parse(raw.get("price"))
    image_index = raw.pop("image_index", None)
    return ExtractedEvent.model_validate({**raw, "price": price, "currency": currency}), image_index


def main(old_dir: Path, new_dir: Path) -> None:
    old = sqlite3.connect(old_dir / "where-to-go.sqlite3")
    old.row_factory = sqlite3.Row
    target = Container.build(new_dir)
    marks = {r["event_id"]: r for r in rows(old, "marks")}
    with target.db.session() as s:
        for seeded in s.exec(select(Tag)):
            s.delete(seeded)
        s.commit()
        for r in rows(old, "settings"):
            s.merge(Setting(key=r["key"], value=json.loads(r["value"])))
        s.add_all(City(id=r["id"], name=r["name"], timezone=r["timezone"]) for r in rows(old, "cities"))
        s.add_all(Tag(id=r["id"], name=r["name"], position=r["position"], is_fallback=bool(r["is_fallback"])) for r in rows(old, "tags"))
        s.add_all(
            Source(id=r["id"], city_id=r["city_id"], handle=r["handle"], title=r["title"], last_refreshed_at=stamp(r["last_refreshed_at"]), last_error=r["last_error"])
            for r in rows(old, "sources")
        )
        s.add_all(
            Post(
                id=r["id"],
                source_id=r["source_id"],
                external_id=r["external_id"],
                url=r["url"],
                published_at=stamp(r["published_at"]),
                text=r["text"],
                image_paths=json.loads(r["image_paths"]),
                processed_at=stamp(r["processed_at"]),
                process_error=r["process_error"],
            )
            for r in rows(old, "posts")
        )
        for r in rows(old, "events"):
            mark = marks.get(r["id"])
            s.add(
                Event(
                    id=r["id"],
                    city_id=r["city_id"],
                    title=r["title"],
                    original_title=r["original_title"],
                    description=r["description"],
                    kind=r["kind"],
                    start_date=date.fromisoformat(r["start_date"]),
                    interest=mark["interest"] if mark else None,
                    plan=Plan(mark["plan"]) if mark and mark["plan"] else None,
                    marked_at=stamp(mark["updated_at"]) if mark else None,
                )
            )
        s.commit()
        for r in rows(old, "mentions"):
            data, image_index = mention_data(json.loads(r["data"]))
            s.add(Mention(id=r["id"], post_id=r["post_id"], event_id=r["event_id"], item_index=r["item_index"], data=data, image_index=image_index, locked=bool(r["locked"])))
        s.add_all(
            Place(id=r["id"], city_id=r["city_id"], post_id=r["post_id"], name=r["name"], address=r["address"], description=r["description"])
            for r in rows(old, "places")
        )
        s.commit()
    for city in target.cities.all():
        for event in target.events.in_city(city.id):
            target.cards.refresh(event.id)
    target.sources.recount_events(target.events)
    if (old_dir / "images").is_dir():
        shutil.copytree(old_dir / "images", new_dir / "images", dirs_exist_ok=True)
    print(f"cities={len(target.cities.all())} cards={sum(len(target.events.in_city(c.id)) for c in target.cities.all())}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
