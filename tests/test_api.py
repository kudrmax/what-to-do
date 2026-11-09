import time
from datetime import timedelta

import pytest
import respx
from fastapi.testclient import TestClient

from tests.helpers import channel_page, extraction_by_text, judge_same_titles, raw_event
from where_to_go.api import create_app
from where_to_go.container import Container


@pytest.fixture
def client(tmp_path):
    extraction = extraction_by_text({"квиз": [raw_event("Квиз", "2099-01-02", "20:00", tags=["Игры и квизы"])]})
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles()))
    with TestClient(app) as test_client:
        yield test_client


def test_empty_app_asks_for_a_city_first(client):
    assert client.get("/sources").status_code == 409
    assert client.get("/settings").json()["active_city_id"] is None


def test_first_city_becomes_active(client):
    city = client.post("/cities", json={"name": "Белград", "timezone": "Europe/Belgrade"}).json()
    assert city["active"] is True
    assert client.post("/cities", json={"name": "Х", "timezone": "Mars/Base"}).status_code == 422


@respx.mock
def test_add_source_refresh_and_mark(client):
    respx.route(host="testserver").pass_through()
    respx.get("https://t.me/s/quizbg").respond(
        200, text=channel_page("quizbg", [(3, "2098-12-30T10:00:00+00:00", "квиз в пятницу")])
    )
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"x", headers={"content-type": "image/jpeg"})
    client.post("/cities", json={"name": "Белград", "timezone": "Europe/Belgrade"})

    source = client.post("/sources", json={"link": "https://t.me/quizbg"})
    assert source.status_code == 201, source.text
    assert source.json()["title"] == "Канал quizbg"
    assert client.post("/sources", json={"link": "@quizbg"}).status_code == 409

    client.app.state.container.refresh.HISTORY = timedelta(days=365 * 100)
    assert client.post("/refresh").status_code == 202
    status = client.get("/refresh").json()
    for _ in range(100):
        if not status["running"]:
            break
        time.sleep(0.02)
        status = client.get("/refresh").json()
    assert status["stage"] == "done", status

    feed = client.get("/events", params={"start": "2099-01-01", "end": "2099-01-07"}).json()
    [item] = feed
    assert item["event"]["title"] == "Квиз" and item["event"]["tags"] == ["Игры и квизы"]
    assert item["event"]["image_url"].startswith("/images/")
    assert client.get(item["event"]["image_url"]).status_code == 200

    event_id = item["event"]["id"]
    marked = client.put(f"/events/{event_id}/mark", json={"interest": 2, "plan": "no"}).json()
    assert marked["mark"] == {"interest": 2, "plan": "no"}
    assert client.get("/events", params={"start": "2099-01-01", "end": "2099-01-07"}).json() == []
    detail = client.get(f"/events/{event_id}").json()
    assert detail["mentions"][0]["post_url"] == "https://t.me/quizbg/3"
    assert client.get("/sources").json()[0]["events_found"] == 1
