"""Opening a database of 1.15: the one global card language becomes the city's, and nothing is read again."""

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from where_to_go.db import Database
from where_to_go.models import City, CollectedPost, Source
from where_to_go.reading_rules import ReadingRules
from where_to_go.repositories import CityRepository, PostRepository, SettingsRepository, SourceRepository

OLD_FINGERPRINT = f"{ReadingRules.POSTS}:1a2b3c4d"


def database_of_1_15(path, language: str | None) -> None:
    """A database as 1.15 left it: no country, card language or settled time labels; the language in settings, if changed."""
    db = Database(path)
    city = CityRepository(db, SettingsRepository(db)).add(City(name="Белград", timezone="Europe/Belgrade"))
    source = SourceRepository(db).add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    posts = PostRepository(db)
    for number in (1, 2):
        posts.add_new(source.id, CollectedPost(external_id=number, url=f"https://t.me/kafana/{number}", published_at=datetime(2026, 11, 1, tzinfo=UTC), text="x"), [])
    read, unread = posts.unprocessed([source.id])
    posts.mark_processed(read.id, OLD_FINGERPRINT)
    db.close()
    with sqlite3.connect(path) as raw:
        for table, column in (("cities", "card_language"), ("cities", "country"), ("web_sites", "times_settled")):
            raw.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        if language is not None:
            raw.execute("INSERT INTO settings (key, value) VALUES ('description_language', ?)", (json.dumps(language),))


@pytest.mark.parametrize("stored,language", [(None, "русский"), ("English", "English")])
def test_the_city_takes_the_language_its_posts_were_read_in(tmp_path, stored, language):
    path = tmp_path / "where-to-go.sqlite3"
    database_of_1_15(path, stored)

    db = Database(path)
    [city] = CityRepository(db, SettingsRepository(db)).all()
    assert (city.name, city.country, city.card_language) == ("Белград", "", language)
    read, unread = sorted(PostRepository(db).to_read([1], "", 20, datetime(2026, 11, 2).date()), key=lambda p: p.external_id)
    assert read.read_with == OLD_FINGERPRINT + ReadingRules.language_part(language)
    assert unread.read_with is None
    db.close()


def test_after_the_migration_the_same_wish_and_language_read_nothing_again(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    database_of_1_15(path, None)
    with sqlite3.connect(path) as raw:
        raw.execute("UPDATE posts SET read_with = ? WHERE read_with IS NOT NULL", (ReadingRules.POSTS,))

    db = Database(path)
    rules = ReadingRules.posts("", "русский")
    assert [p.external_id for p in PostRepository(db).to_read([1], rules, 20, datetime(2026, 11, 2).date())] == [2]  # only the unread one
    db.close()


def test_a_second_opening_migrates_nothing_twice(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    database_of_1_15(path, None)
    Database(path).close()
    db = Database(path)
    [read] = [p for p in PostRepository(db).to_read([1], "", 20, datetime(2026, 11, 2).date()) if p.read_with]
    assert read.read_with.count(":lang-") == 1
    db.close()


def test_sites_added_before_keep_their_decided_time_labels(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    database_of_1_15(path, None)
    db = Database(path)
    with db.engine.connect() as connection:
        default = [row for row in connection.exec_driver_sql("PRAGMA table_info(web_sites)") if row[1] == "times_settled"][0][4]
    assert default == "'1'"
    db.close()
