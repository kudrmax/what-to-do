"""Opening a database of 1.28: every card gets the photos of its posts."""

import sqlite3
from datetime import UTC, date, datetime

from tests.helpers import mention
from where_to_go.db import Database
from where_to_go.models import City, Event, Mention, Post, Source
from where_to_go.repositories import EventRepository


def database_of_1_28(path) -> int:
    db = Database(path)
    with db.session() as s:
        s.add(City(id=1, name="Белград", timezone="Europe/Belgrade"))
        s.add(Source(id=1, city_id=1, handle="eje", title="EJE"))
        s.add(Post(id=1, source_id=1, external_id=1, url="u1", published_at=datetime(2026, 11, 1, tzinfo=UTC), text="", image_paths=["a.jpg", "v-f0.jpg", "v-f1.jpg"]))
        s.add(Post(id=2, source_id=1, external_id=2, url="u2", published_at=datetime(2026, 11, 2, tzinfo=UTC), text="", image_paths=["x.jpg", "y.jpg"]))
        card = Event(city_id=1, title="Вечер", original_title="", description="", kind="single", start_date=date(2026, 11, 20), image_path="v-f1.jpg")
        other = Event(city_id=1, title="Другой", original_title="", description="", kind="single", start_date=date(2026, 11, 21))
        s.add(card)
        s.add(other)
        s.commit()
        card_id, other_id = card.id, other.id
        data = mention(1).data
        s.add(Mention(post_id=1, event_id=card_id, item_index=0, data=data, image_index=2))
        s.add(Mention(post_id=2, event_id=card_id, item_index=0, data=data, image_index=1))
        s.add(Mention(post_id=2, event_id=other_id, item_index=1, data=data, image_index=0))
        s.commit()
    db.close()
    with sqlite3.connect(path) as raw:
        raw.execute("ALTER TABLE events DROP COLUMN image_paths")
    return card_id


def test_cards_of_1_28_get_the_photos_of_their_posts(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    card_id = database_of_1_28(path)

    db = Database(path)
    assert EventRepository(db).get(card_id).image_paths == ["v-f1.jpg", "a.jpg", "y.jpg"]
    db.close()
