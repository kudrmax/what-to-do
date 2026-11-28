"""Sources keep the user's order: the Sources screen shows it and a refresh reads posts and photos in it."""

import sqlite3
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from tests.helpers import BELGRADE, add_city, channel_page, extraction_by_text, judge_same_titles, photos_saying
from tests.test_photos import read_posts, store, transcriber
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.db import Database
from where_to_go.models import City, CollectedPost, Post, Source, SourceStatus
from where_to_go.refresh import Stage
from where_to_go.repositories import PostRepository, SourceRepository

DAY = datetime(2026, 11, 20, tzinfo=UTC)


def city(db: Database, name: str) -> int:
    from sqlmodel import Session

    with Session(db.engine) as s:
        added = City(name=name, country="Сербия", timezone="Europe/Belgrade")
        s.add(added)
        s.commit()
        s.refresh(added)
        return added.id


def database_before_source_order(path) -> tuple[int, int]:
    db = Database(path)
    belgrade, novi_sad = city(db, "Белград"), city(db, "Нови Сад")
    sources = SourceRepository(db)
    for handle, title, status, city_id in [
        ("b", "бар", SourceStatus.NEW, belgrade),
        ("a", "Афиша", SourceStatus.NEW, belgrade),
        ("z", "Зал", SourceStatus.FAVORITE, belgrade),
        ("c", "Clubs", SourceStatus.FAVORITE, belgrade),
        ("x", "Xyz", SourceStatus.NEW, novi_sad),
        ("d", "Dom", SourceStatus.NEW, novi_sad),
    ]:
        sources.add(Source(city_id=city_id, handle=handle, title=title, status=status))
    db.close()
    with sqlite3.connect(path) as raw:
        raw.execute("ALTER TABLE sources DROP COLUMN position")
    return belgrade, novi_sad


def titles(sources: list[Source]) -> list[str]:
    return [s.title for s in sources]


def test_sources_of_an_older_database_keep_the_order_they_were_shown_in(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    belgrade, novi_sad = database_before_source_order(path)

    sources = SourceRepository(Database(path))

    assert titles(sources.in_city(belgrade)) == ["Clubs", "Зал", "Афиша", "бар"]
    assert [s.position for s in sources.in_city(belgrade)] == [0, 1, 2, 3]
    assert titles(sources.in_city(novi_sad)) == ["Dom", "Xyz"]
    assert [s.position for s in sources.in_city(novi_sad)] == [0, 1]


def test_a_new_source_goes_last_in_its_own_city(tmp_path):
    path = tmp_path / "where-to-go.sqlite3"
    belgrade, novi_sad = database_before_source_order(path)
    sources = SourceRepository(Database(path))

    added = sources.add(Source(city_id=novi_sad, handle="n", title="Аа"))

    assert added.position == 2
    assert titles(sources.in_city(novi_sad)) == ["Dom", "Xyz", "Аа"]
    assert sources.add(Source(city_id=belgrade, handle="n", title="Аа")).position == 4


def test_the_first_source_of_a_city_comes_first(tmp_path):
    db = Database(tmp_path / "where-to-go.sqlite3")
    sources = SourceRepository(db)
    belgrade = city(db, "Белград")

    assert [sources.add(Source(city_id=belgrade, handle=h, title=h)).position for h in ("b", "a")] == [0, 1]
    assert titles(sources.in_city(belgrade)) == ["b", "a"]


# ---------- the order API ----------


@pytest.fixture
def client(tmp_path):
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as test_client:
        yield test_client


def sources_of(client, city_id: int, *handles: str) -> list[int]:
    c = client.app.state.container
    return [c.sources.add(Source(city_id=city_id, handle=h, title=h)).id for h in handles]


def test_sources_are_listed_and_reordered_in_the_users_order(client):
    city_id = client.post("/cities", json=BELGRADE).json()["id"]
    first, second, third = sources_of(client, city_id, "a", "b", "c")
    client.put(f"/sources/{second}/paused", json={"paused": True})
    assert [s["id"] for s in client.get("/sources").json()] == [first, second, third]

    reordered = client.put("/sources/order", json={"ids": [third, second, first]})

    assert reordered.status_code == 200, reordered.text
    assert [s["id"] for s in reordered.json()] == [third, second, first]
    assert [s["id"] for s in client.get("/sources").json()] == [third, second, first]


def test_an_order_that_is_not_exactly_the_active_citys_sources_changes_nothing(client):
    city_id = client.post("/cities", json=BELGRADE).json()["id"]
    first, second = sources_of(client, city_id, "a", "b")
    other_city = add_city(client.app.state.container, "Нови Сад", "Europe/Belgrade")
    [elsewhere] = sources_of(client, other_city.id, "x")

    for ids in ([second], [second, first, elsewhere], [second, elsewhere], [second, first, first], [second, first, 999]):
        assert client.put("/sources/order", json={"ids": ids}).status_code == 422, ids

    assert [s["id"] for s in client.get("/sources").json()] == [first, second]


# ---------- reading order ----------


def post(posts: PostRepository, source_id: int, external_id: int, hours: int) -> None:
    published = DAY + timedelta(hours=hours)
    posts.add_new(source_id, CollectedPost(external_id=external_id, url=f"https://t.me/s{source_id}/{external_id}", published_at=published, text="т"), [])


def test_posts_are_read_by_source_order_and_newest_first_inside_a_source(tmp_path):
    db = Database(tmp_path / "where-to-go.sqlite3")
    sources, posts = SourceRepository(db), PostRepository(db)
    belgrade = city(db, "Белград")
    first = sources.add(Source(city_id=belgrade, handle="a", title="a")).id
    second = sources.add(Source(city_id=belgrade, handle="b", title="b")).id
    for source_id, external_id, hours in [(first, 1, 1), (second, 1, 2), (first, 2, 5), (second, 2, 0), (first, 3, 3)]:
        post(posts, source_id, external_id, hours)
    sources.reorder(belgrade, [second, first])

    chosen = posts.to_read([first, second], "rules", 20, date(2026, 11, 20))

    assert [(p.source_id, p.external_id) for p in chosen] == [(second, 1), (second, 2), (first, 2), (first, 3), (first, 1)]


def test_photos_are_listed_in_the_order_of_their_posts():
    photos, _ = transcriber(photos_saying(), store("new.jpg", "old.jpg", "shared.jpg"))
    newer = Post(id=1, source_id=1, external_id=2, url="u", published_at=DAY, text="t", image_paths=["new.jpg", "shared.jpg"])
    older = Post(id=2, source_id=1, external_id=1, url="u", published_at=DAY - timedelta(days=1), text="t", image_paths=["shared.jpg", "old.jpg"])

    names = photos.untranscribed([newer, older])

    assert names == ["new.jpg", "shared.jpg", "old.jpg"]
    assert photos.batches(names) == [names]


@respx.mock
async def test_a_refresh_sends_photos_and_posts_in_source_order(tmp_path):
    recent = datetime.now(UTC) - timedelta(days=2)
    respx.get(url__startswith="https://cdn.test/").mock(
        side_effect=lambda request: httpx.Response(200, content=request.url.path.encode(), headers={"content-type": "image/jpeg"})
    )
    respx.get("https://t.me/s/kafana").respond(200, text=channel_page("kafana", [(1, recent.isoformat(), "раньше"), (2, (recent + timedelta(hours=1)).isoformat(), "позже")]))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(3, recent.isoformat(), "афиша")]))
    extraction, photo_llm = extraction_by_text({}), photos_saying()
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photo_llm, http=httpx.AsyncClient())
    belgrade = add_city(container, "Белград", "Europe/Belgrade")
    kafana = container.sources.add(Source(city_id=belgrade.id, handle="kafana", title="Кафана"))
    afisha = container.sources.add(Source(city_id=belgrade.id, handle="afisha", title="Афиша"))
    container.sources.reorder(belgrade.id, [afisha.id, kafana.id])

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE, progress.errors
    assert [image.data for call in photo_llm.images for image in call] == [b"/3.jpg", b"/2.jpg", b"/1.jpg"]
    assert [item["text"] for item in read_posts(extraction)] == ["афиша", "позже", "раньше"]
    await container.close()
