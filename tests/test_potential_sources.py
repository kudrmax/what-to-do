import json
from datetime import UTC, datetime, timedelta

import httpx
import respx
from fastapi.testclient import TestClient

from tests.helpers import FakeLlm, channel_page, judge_same_titles, photos_saying
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.models import Source
from where_to_go.refresh import Stage
from where_to_go.telegram import TelegramPageParser

EARLIER = (datetime.now(UTC) - timedelta(days=3)).isoformat()
RECENT = (datetime.now(UTC) - timedelta(days=2)).isoformat()
LATER = (datetime.now(UTC) - timedelta(days=1)).isoformat()


def pointing(channels_by_marker: dict[str, list[dict]]) -> FakeLlm:
    """Extraction fake: a post whose text contains a marker points to the given channels."""

    def answer(_: str, prompt: str) -> dict:
        posts = json.loads(prompt.split("\n", 1)[1])
        result = []
        for post in posts:
            channels = [c for marker, found in channels_by_marker.items() if marker in post["text"] for c in found]
            result.append({"post_id": post["post_id"], "events": [], "places": [], "channels": channels})
        return {"posts": result}

    return FakeLlm(answer)


def link(handle: str) -> dict:
    return {"handle": handle, "via": "link"}


def forward(handle: str) -> dict:
    return {"handle": handle, "via": "forward"}


async def build(tmp_path, extraction) -> Container:
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    city = container.cities.add("Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
    return container


def serve(kafana_posts, afisha_posts=()):
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"img", headers={"content-type": "image/jpeg"})
    respx.get("https://t.me/s/kafana").respond(200, text=channel_page("kafana", list(kafana_posts)))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", list(afisha_posts)))


async def refresh(container: Container) -> None:
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.stage is Stage.DONE, progress.errors


def handles(container: Container) -> list[str]:
    return [p.handle for p in container.potential_sources.in_city(1) if not p.processed]


def test_a_forwarded_post_says_where_it_comes_from():
    page = channel_page("bg", [(5, RECENT, "Лекция в пятницу")]).replace(
        '<div class="tgme_widget_message_text">',
        '<div class="tgme_widget_message_forwarded_from accent_color">Forwarded from&nbsp;'
        '<a class="tgme_widget_message_forwarded_from_name" href="https://t.me/lectures_bg/10"><span dir="auto">Лекции</span></a></div>'
        '<div class="tgme_widget_message_text">',
    )
    [post] = TelegramPageParser(page).posts()
    assert post.text == "Переслано из Лекции (https://t.me/lectures_bg/10)\n\nЛекция в пятницу"


@respx.mock
async def test_channels_a_post_points_to_are_kept_with_the_post_they_came_from(tmp_path):
    extraction = pointing({"пересылка": [forward("lectures_bg"), link("t.me/s/quiz_bg")]})
    container = await build(tmp_path, extraction)
    serve([(1, RECENT, "пересылка лекции")])

    await refresh(container)

    found = {p.handle: p for p in container.potential_sources.in_city(1)}
    assert set(found) == {"lectures_bg", "quiz_bg"}
    [origin] = found["lectures_bg"].origins
    assert (origin.via, origin.source_title, origin.post_url) == ("forward", "Кафана", "https://t.me/kafana/1")
    assert found["quiz_bg"].url == "https://t.me/quiz_bg"
    assert "channels" in json.dumps(extraction.schemas[0])
    await container.close()


@respx.mock
async def test_own_channel_known_sources_bots_and_non_channels_are_not_potential_sources(tmp_path):
    channels = [link("kafana"), link("@Afisha"), link("tickets_bot"), link("https://t.me/+AbCdEf"), link("https://example.com"), link("new_one")]
    container = await build(tmp_path, pointing({"ссылки": channels}))
    serve([(1, RECENT, "ссылки")])

    await refresh(container)

    assert handles(container) == ["new_one"]
    await container.close()


@respx.mock
async def test_a_channel_pointed_to_again_gets_another_post_not_a_duplicate(tmp_path):
    container = await build(tmp_path, pointing({"ссылка": [link("lectures_bg")], "снова": [link("Lectures_BG"), forward("lectures_bg")]}))
    serve([(1, RECENT, "ссылка")], [(2, LATER, "снова")])

    await refresh(container)

    [found] = container.potential_sources.in_city(1)
    assert [(o.post_url, o.via) for o in found.origins] == [("https://t.me/afisha/2", "forward"), ("https://t.me/kafana/1", "link")]
    await container.close()


@respx.mock
async def test_a_processed_channel_never_comes_back(tmp_path):
    container = await build(tmp_path, pointing({"ссылка": [link("lectures_bg")]}))
    serve([(1, EARLIER, "ссылка")])
    await refresh(container)
    [found] = container.potential_sources.in_city(1)
    container.potential_sources.mark(found.id, True)

    serve([(1, EARLIER, "ссылка"), (3, LATER, "опять ссылка")])
    await refresh(container)

    [still] = container.potential_sources.in_city(1)
    assert still.processed
    assert len(still.origins) == 1
    await container.close()


@respx.mock
async def test_a_post_read_again_replaces_what_it_pointed_to(tmp_path):
    answers = {"пост": [link("old_one")]}
    container = await build(tmp_path, pointing(answers))
    serve([(1, RECENT, "пост")])
    await refresh(container)

    answers["пост"] = [link("new_one")]
    container.settings.update(extraction_prompt=container.settings.load().extraction_prompt + "\nRead the photos too.")
    await refresh(container)

    assert handles(container) == ["new_one"]
    await container.close()


@respx.mock
async def test_a_channel_added_as_a_source_leaves_the_list(tmp_path):
    container = await build(tmp_path, pointing({"ссылка": [link("lectures_bg")]}))
    serve([(1, RECENT, "ссылка")])
    await refresh(container)

    container.sources.add(Source(city_id=1, handle="Lectures_bg", title="Лекции"))

    assert handles(container) == []
    await container.close()


@respx.mock
async def test_most_pointed_to_channels_come_first(tmp_path):
    container = await build(tmp_path, pointing({"раз": [link("once")], "два": [link("twice")]}))
    serve([(1, LATER, "раз"), (2, RECENT, "два")], [(3, RECENT, "два")])

    await refresh(container)

    assert handles(container) == ["twice", "once"]
    await container.close()


@respx.mock
def test_potential_sources_are_listed_and_marked_through_the_api(tmp_path):
    extraction = pointing({"ссылка": [link("lectures_bg")]})
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as client:
        respx.route(host="testserver").pass_through()
        respx.get("https://t.me/s/kafana").respond(200, text=channel_page("kafana", [(1, RECENT, "ссылка")]))
        respx.get(url__startswith="https://cdn.test/").respond(200, content=b"x", headers={"content-type": "image/jpeg"})
        client.post("/cities", json={"name": "Белград", "timezone": "Europe/Belgrade"})
        client.post("/sources", json={"link": "kafana"})
        client.post("/refresh")
        while client.get("/refresh").json()["running"]:
            pass

        [found] = client.get("/potential-sources").json()
        assert (found["handle"], found["processed"], found["url"]) == ("lectures_bg", False, "https://t.me/lectures_bg")
        assert found["origins"][0]["source_title"]

        assert client.put(f"/potential-sources/{found['id']}/processed", json={"processed": True}).status_code == 204
        assert client.get("/potential-sources").json()[0]["processed"] is True
        assert client.put("/potential-sources/999/processed", json={"processed": True}).status_code == 404
