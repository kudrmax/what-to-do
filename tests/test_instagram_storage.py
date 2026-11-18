import sqlite3
from datetime import UTC, datetime

import pytest
from sqlmodel import select

from tests.helpers import add_city
from where_to_go.container import Container
from where_to_go.db import Database
from where_to_go.models import CollectedPost, InstagramReading, Post, Source, SourceKind, SourcePublic
from where_to_go.repositories import PostRepository

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
async def app(tmp_path):
    container = Container.build(tmp_path)
    city = add_city(container, "Белград", "Europe/Belgrade")
    source = container.sources.add(Source(kind=SourceKind.INSTAGRAM, handle="eje.belgrade", title="EJE", city_id=city.id))
    yield container, source
    await container.close()


def test_the_link_of_an_instagram_source_is_its_profile(app):
    _, source = app
    assert SourcePublic.model_validate(source, from_attributes=True).url == "https://www.instagram.com/eje.belgrade/"


async def test_a_new_instagram_source_reads_everything(app):
    container, source = app
    container.instagram.add(source.id, InstagramReading())
    assert container.instagram.reading(source.id) == InstagramReading(posts=True, stories=True)


async def test_what_is_read_can_be_changed(app):
    container, source = app
    container.instagram.add(source.id, InstagramReading())
    changed = container.instagram.change(source.id, InstagramReading(posts=True, stories=False))
    assert changed == InstagramReading(posts=True, stories=False)
    assert container.instagram.readings([source.id]) == {source.id: changed}


async def test_deleting_the_source_deletes_its_reading(app):
    container, source = app
    container.instagram.add(source.id, InstagramReading())
    with container.db.session() as s:
        s.delete(s.get(Source, source.id))
        s.commit()
    assert container.instagram.readings([source.id]) == {}


async def test_a_skipped_post_is_known_but_never_read(app):
    container, source = app
    skipped = CollectedPost(external_id=7, url="https://www.instagram.com/stories/highlights/7/", published_at=NOW, text="", read=False, video_urls=["https://v"])
    assert container.posts.add_new(source.id, skipped, [])
    assert 7 in container.posts.known_ids(source.id)
    assert container.posts.unprocessed([source.id]) == []
    with container.db.session() as s:
        stored = s.exec(select(Post).where(Post.source_id == source.id)).one()
    assert stored.read_with == PostRepository.SKIPPED
    assert stored.processed_at is not None


async def test_a_read_post_waits_for_reading(app):
    container, source = app
    container.posts.add_new(source.id, CollectedPost(external_id=8, url="u", published_at=NOW, text="t", video_urls=["https://v"]), [])
    [post] = container.posts.unprocessed([source.id])
    assert post.external_id == 8 and post.read_with is None


def test_an_old_database_gets_the_table_of_instagram_sources(tmp_path):
    path = tmp_path / "old.sqlite3"
    Database(path).close()
    with sqlite3.connect(path) as old:
        old.execute("DROP TABLE instagram_profiles")
    Database(path).close()
    with sqlite3.connect(path) as upgraded:
        assert {row[1] for row in upgraded.execute("PRAGMA table_info(instagram_profiles)")} == {"source_id", "posts", "stories"}
