import json
import time

import pytest
from fastapi.testclient import TestClient

from tests.helpers import FakeLlm, judge_same_titles, photos_saying, raw_event
from tests.test_api import seeded
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.refresh import Stage

NEW_TAGS = {"Джазовый вечер": ["Концерт", "Джаз", "Выдумка"], "Квиз": [], "Прошлый концерт": ["Джаз"]}


def by_title(system, prompt):
    cards = json.loads(prompt.split("\n", 1)[1])
    return {"cards": [{"id": card["id"], "tags": NEW_TAGS[card["title"]]} for card in cards]}


@pytest.fixture
def retagging():
    return FakeLlm(by_title)


@pytest.fixture
def client(tmp_path, retagging):
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=retagging, matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as test_client:
        yield test_client


def finished(client):
    status = client.get("/tags/retag").json()
    for _ in range(100):
        if not status["running"]:
            return status
        time.sleep(0.02)
        status = client.get("/tags/retag").json()
    raise AssertionError(status)


def test_retagging_gives_upcoming_cards_and_their_announcements_new_tags(client, retagging):
    jazz, quiz, past = seeded(
        client,
        ("a", raw_event("Джазовый вечер", "2099-01-02", tags=["Концерт"])),
        ("a", raw_event("Квиз", "2099-01-03", tags=["Игры и квизы"])),
        ("a", raw_event("Прошлый концерт", "2020-01-03", tags=["Концерт"])),
    )
    jazz_tag = client.post("/tags", json={"name": "Джаз", "description": "джазовые концерты и джем-сейшены"}).json()
    assert jazz_tag["description"] == "джазовые концерты и джем-сейшены"
    assert client.get("/tags/retag").json() | {"upcoming": 2, "claude_calls": 1} == client.get("/tags/retag").json()

    assert client.post("/tags/retag").status_code == 202
    status = finished(client)

    assert (status["cards_retagged"], status["cards_changed"], status["errors"]) == (2, 2, [])
    assert client.get(f"/events/{jazz}").json()["tags"] == ["Концерт", "Джаз"]
    assert client.get(f"/events/{quiz}").json()["tags"] == ["Другое"]
    assert client.get(f"/events/{past}").json()["tags"] == ["Концерт"]
    c = client.app.state.container
    c.cards.refresh(jazz)
    assert client.get(f"/events/{jazz}").json()["tags"] == ["Концерт", "Джаз"]
    [(system, _)] = retagging.calls
    assert '"Джаз" — джазовые концерты и джем-сейшены' in system


def test_tag_meaning_can_be_changed_and_cleared(client):
    seeded(client, ("a", raw_event("Квиз", "2099-01-03")))
    tag = client.get("/tags").json()[0]
    described = client.patch(f"/tags/{tag['id']}", json={"description": "  что угодно  "}).json()
    assert (described["name"], described["description"]) == (tag["name"], "что угодно")
    renamed = client.patch(f"/tags/{tag['id']}", json={"name": "Новое"}).json()
    assert (renamed["name"], renamed["description"]) == ("Новое", "что угодно")
    assert client.patch(f"/tags/{tag['id']}", json={"description": ""}).json()["description"] == ""
    assert client.patch("/tags/999", json={"description": "x"}).status_code == 404


def test_refresh_and_retagging_do_not_run_together(client):
    seeded(client, ("a", raw_event("Квиз", "2099-01-03")))
    c = client.app.state.container
    c.retag.progress.active = True
    assert client.post("/refresh").status_code == 409
    c.retag.progress.active = False
    c.refresh.progress.stage = Stage.READING
    assert client.post("/tags/retag").status_code == 409
    c.refresh.progress.stage = Stage.DONE


def test_changed_cards_add_up_across_batches_read_at_once(client, monkeypatch):
    from where_to_go.retagging import EventRetagger

    monkeypatch.setattr(EventRetagger, "BATCH_SIZE", 1)
    seeded(client, ("a", raw_event("Джазовый вечер", "2099-01-02", tags=["Концерт"])), ("a", raw_event("Квиз", "2099-01-03", tags=["Игры и квизы"])))
    client.post("/tags", json={"name": "Джаз"})
    client.post("/tags/retag")
    status = finished(client)
    assert (status["claude_calls"], status["cards_changed"]) == (2, 2)


def test_retagging_without_a_usable_claude_code_says_so_once(tmp_path, monkeypatch):
    from tests.helpers import FakeClaude
    from where_to_go.installed_cli import CliStatus
    from where_to_go.llm import ClaudeUnavailableError
    from where_to_go.retagging import EventRetagger

    missing = FakeClaude(CliStatus.MISSING).found

    class Unavailable:
        async def complete_json(self, system, prompt, schema, images=()):
            raise ClaudeUnavailableError(missing)

    monkeypatch.setattr(EventRetagger, "BATCH_SIZE", 1)
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=Unavailable(), matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as client:
        seeded(client, ("a", raw_event("Джазовый вечер", "2099-01-02")), ("a", raw_event("Квиз", "2099-01-03")))
        client.post("/tags/retag")
        status = finished(client)

    assert status["claude_calls"] == 2
    assert status["errors"] == ["Install Claude Code to read posts"]
