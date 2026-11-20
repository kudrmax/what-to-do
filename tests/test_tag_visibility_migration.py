"""Opening a database of 1.27: a hidden tag keeps hiding events only when every tag of the event is hidden."""

import sqlite3

from where_to_go.db import Database
from where_to_go.models import TagVisibility
from where_to_go.repositories import TagRepository


def database_of_1_27(path) -> None:
    db = Database(path)
    TagRepository(db).seed(["Концерт", "Детям"], "Другое")
    db.close()
    with sqlite3.connect(path) as raw:
        raw.execute("ALTER TABLE tags DROP COLUMN visibility")
        raw.execute("ALTER TABLE tags ADD COLUMN hidden BOOLEAN NOT NULL DEFAULT '0'")
        raw.execute("UPDATE tags SET hidden = 1 WHERE name = 'Детям'")


def test_hidden_tags_of_1_27_stay_hidden_and_the_rest_stay_shown(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    database_of_1_27(path)

    db = Database(path)
    visibility = {t.name: t.visibility for t in TagRepository(db).all()}
    assert visibility == {"Концерт": TagVisibility.SHOWN, "Детям": TagVisibility.HIDDEN, "Другое": TagVisibility.SHOWN}
    db.close()


def test_a_new_tag_of_a_migrated_database_is_shown(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    database_of_1_27(path)

    db = Database(path)
    assert TagRepository(db).add("Джаз").visibility is TagVisibility.SHOWN
    db.close()
