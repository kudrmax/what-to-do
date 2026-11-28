"""A refresh with a limit downloads everything but reads only the next posts in the user's order of sources."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from tests.helpers import BELGRADE, FakeLlm, add_city, channel_page, extraction_by_text, judge_same_titles, photos_saying, wait_until
from tests.test_photos import read_posts
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.llm import LlmError
from where_to_go.models import Source
from where_to_go.refresh import Stage
from where_to_go.settings import AppSettings

RECENT = datetime.now(UTC) - timedelta(days=2)
LONG_AGO = (datetime.now(UTC) - timedelta(days=60)).isoformat()


def at(hours: int) -> str:
    return (RECENT + timedelta(hours=hours)).isoformat()


def serve_images() -> None:
    respx.get(url__startswith="https://cdn.test/").mock(
        side_effect=lambda request: httpx.Response(200, content=request.url.path.encode(), headers={"content-type": "image/jpeg"})
    )


def serve_two_channels() -> None:
    serve_images()
    respx.get("https://t.me/s/kafana").respond(200, text=channel_page("kafana", [(1, at(0), "кафана раньше"), (2, at(1), "кафана позже")]))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(3, at(0), "афиша")]))


class SwitchablePhotos:
    """Photo reader fake that fails while `failing` is set."""

    def __init__(self) -> None:
        self.failing = False
        self.working = photos_saying()
        self.images: list[bytes] = []

    async def complete_json(self, system, prompt, schema, images=()):
        self.images += [image.data for image in images]
        if self.failing:
            raise LlmError("rate limited")
        return await self.working.complete_json(system, prompt, schema, images)


async def two_channels(tmp_path, photo_llm) -> tuple[Container, FakeLlm]:
    extraction = extraction_by_text({})
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photo_llm, http=httpx.AsyncClient())
    belgrade = add_city(container, "Белград", "Europe/Belgrade")
    kafana = container.sources.add(Source(city_id=belgrade.id, handle="kafana", title="Кафана"))
    afisha = container.sources.add(Source(city_id=belgrade.id, handle="afisha", title="Афиша"))
    container.sources.reorder(belgrade.id, [afisha.id, kafana.id])
    return container, extraction


async def refresh(container: Container, limit: int | None = None):
    container.refresh.start(limit)
    progress = await container.refresh.wait()
    assert progress.stage is Stage.DONE, progress.errors
    return progress


@respx.mock
async def test_a_limited_refresh_reads_the_first_posts_in_source_order_and_the_next_one_continues(tmp_path):
    serve_two_channels()
    photo_llm = photos_saying()
    container, extraction = await two_channels(tmp_path, photo_llm)

    first = await refresh(container, 2)

    assert [item["text"] for item in read_posts(extraction)] == ["афиша", "кафана позже"]
    assert [image.data for call in photo_llm.images for image in call] == [b"/3.jpg", b"/2.jpg"]
    assert (first.limit, first.new_posts, first.posts_to_read, first.posts_read, first.posts_left) == (2, 3, 2, 2, 1)

    second = await refresh(container, 2)

    assert [item["text"] for item in read_posts(extraction)] == ["афиша", "кафана позже", "кафана раньше"]
    assert (second.posts_to_read, second.posts_read, second.posts_left) == (1, 1, 0)
    await container.close()


@respx.mock
async def test_a_limit_larger_than_the_unread_posts_reads_them_all(tmp_path):
    serve_two_channels()
    container, extraction = await two_channels(tmp_path, photos_saying())

    progress = await refresh(container, 500)

    assert [item["text"] for item in read_posts(extraction)] == ["афиша", "кафана позже", "кафана раньше"]
    assert (progress.limit, progress.posts_read, progress.posts_left) == (500, 3, 0)
    await container.close()


@respx.mock
async def test_a_full_refresh_reads_everything_and_counts_nothing_left(tmp_path):
    serve_two_channels()
    container, extraction = await two_channels(tmp_path, photos_saying())

    progress = await refresh(container)

    assert len(read_posts(extraction)) == 3
    assert (progress.limit, progress.posts_left) == (None, None)
    await container.close()


@respx.mock
async def test_a_post_dropped_because_its_photos_failed_counts_toward_the_limit_and_stays_unread(tmp_path):
    serve_two_channels()
    photo_llm = SwitchablePhotos()
    container, extraction = await two_channels(tmp_path, photo_llm)
    photo_llm.failing = True

    container.refresh.start(1)
    dropped = await container.refresh.wait()

    assert photo_llm.images == [b"/3.jpg"]
    assert (dropped.posts_to_read, dropped.posts_read, dropped.posts_left) == (0, 0, 3)
    assert read_posts(extraction) == []

    photo_llm.failing = False
    retried = await refresh(container, 1)

    assert [item["text"] for item in read_posts(extraction)] == ["афиша"]
    assert retried.posts_left == 2
    await container.close()


@respx.mock
async def test_linked_posts_count_toward_the_limit_in_the_order_of_their_own_source(tmp_path):
    serve_images()
    respx.get("https://t.me/s/umnaya", params={"before": "639"}).respond(200, text=channel_page("umnaya", [(638, LONG_AGO, "умная среда")]))
    respx.get("https://t.me/s/umnaya").respond(200, text=channel_page("umnaya", [(700, at(0), "умная свежая")]))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", [(7, at(5), "дайджест: https://t.me/umnaya/638")]))
    extraction = extraction_by_text({})
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    belgrade = add_city(container, "Белград", "Europe/Belgrade")
    afisha = container.sources.add(Source(city_id=belgrade.id, handle="afisha", title="Афиша"))
    umnaya = container.sources.add(Source(city_id=belgrade.id, handle="umnaya", title="Умная"))
    container.sources.reorder(belgrade.id, [umnaya.id, afisha.id])

    progress = await refresh(container, 2)

    assert [item["text"] for item in read_posts(extraction)] == ["умная свежая", "умная среда"]
    assert (progress.new_posts, progress.posts_left) == (3, 1)
    await container.close()


# ---------- the setting and the API ----------


def test_the_partial_refresh_size_is_a_bounded_setting():
    assert AppSettings().partial_refresh_posts == 30
    for wrong in (0, 501):
        with pytest.raises(ValueError):
            AppSettings(partial_refresh_posts=wrong)


@pytest.fixture
def client(tmp_path):
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as test_client:
        test_client.post("/cities", json=BELGRADE)
        yield test_client


def test_refresh_takes_an_optional_limit(client):
    limited = client.post("/refresh", json={"limit": 30})
    assert limited.status_code == 202, limited.text
    assert limited.json()["limit"] == 30
    wait_until(lambda: not client.get("/refresh").json()["running"])

    full = client.post("/refresh")
    assert full.status_code == 202, full.text
    assert full.json()["limit"] is None


@pytest.mark.parametrize("limit", [0, 501, "many"])
def test_a_limit_out_of_range_is_refused(client, limit):
    assert client.post("/refresh", json={"limit": limit}).status_code == 422
