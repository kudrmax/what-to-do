import pytest
from fastapi.testclient import TestClient

from tests.helpers import BELGRADE, judge_same_titles, photos_saying, extraction_by_text, raw_event
from tests.test_api import seeded
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.refresh import Stage

LONDON = {"name": "London", "country": "United Kingdom", "timezone": "Europe/London", "card_language": "English"}
NEW_YORK = {"name": "New York", "country": "United States", "timezone": "America/New_York", "card_language": "English"}


@pytest.fixture
def client(tmp_path):
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as test_client:
        yield test_client


def test_an_empty_app_has_no_tags_until_its_first_city(client):
    assert client.get("/tags").json() == []


def test_an_english_first_city_brings_english_tags_with_other_last(client):
    city = client.post("/cities", json=LONDON).json()
    assert (city["name"], city["country"], city["card_language"]) == ("London", "United Kingdom", "English")
    names = [t["name"] for t in client.get("/tags").json()]
    assert names[0] == "Concert" and names[-1] == "Other"
    client.post("/cities", json=BELGRADE)
    assert [t["name"] for t in client.get("/tags").json()] == names  # tags are shared: a second city brings none


def test_a_city_in_another_language_gets_english_tags(client):
    client.post("/cities", json={**LONDON, "name": "Lisbon", "country": "Portugal", "timezone": "Europe/Lisbon", "card_language": "Português"})
    assert client.get("/tags").json()[-1]["name"] == "Other"


def test_the_card_language_is_english_when_not_given(client):
    body = {k: v for k, v in LONDON.items() if k != "card_language"}
    assert client.post("/cities", json=body).json()["card_language"] == "English"


def test_a_city_needs_a_country_and_a_known_time_zone(client):
    assert client.post("/cities", json={**LONDON, "country": ""}).status_code == 422
    assert client.post("/cities", json={k: v for k, v in LONDON.items() if k != "country"}).status_code == 422
    unknown = client.post("/cities", json={**LONDON, "timezone": "Mars/Base"})
    assert unknown.status_code == 422 and unknown.json() == {"detail": "Unknown time zone"}


def test_a_second_city_of_the_same_name_is_refused_clearly(client):
    client.post("/cities", json=LONDON)
    twin = client.post("/cities", json={**LONDON, "name": " london ", "country": "Canada", "timezone": "America/Toronto"})
    assert twin.status_code == 409 and "London" in twin.json()["detail"]


def test_a_city_is_edited_field_by_field(client):
    london = client.post("/cities", json=LONDON).json()
    york = client.post("/cities", json=NEW_YORK).json()
    changed = client.patch(f"/cities/{london['id']}", json={"timezone": "Europe/Dublin", "card_language": "русский"}).json()
    assert (changed["name"], changed["timezone"], changed["card_language"]) == ("London", "Europe/Dublin", "русский")
    assert client.patch(f"/cities/{london['id']}", json={"name": "New York"}).status_code == 409
    assert client.patch(f"/cities/{london['id']}", json={"name": "London"}).status_code == 200  # its own name is no duplicate
    assert client.patch(f"/cities/{london['id']}", json={"timezone": "Nowhere/City"}).status_code == 422
    assert client.patch(f"/cities/{london['id']}", json={"country": ""}).status_code == 422
    assert client.patch("/cities/999", json={"name": "X"}).status_code == 404
    assert client.get("/cities").json()[1]["id"] == york["id"]


def test_deleting_a_city_deletes_its_sources_and_cards_and_hands_over_the_feed(client):
    seeded(client, ("kafana", raw_event("Концерт", "2099-01-02")), ("kafana", raw_event("Лекция", "2099-01-03")))
    belgrade = client.get("/settings").json()["active_city_id"]
    london = client.post("/cities", json=LONDON).json()
    [first, _] = [o["event"]["id"] for o in client.get("/events", params={"start": "2099-01-01", "end": "2099-01-07"}).json()]
    client.put(f"/events/{first}/mark", json={"interest": 4, "plan": None})

    assert client.get(f"/cities/{belgrade}/contents").json() == {"sources": 1, "events": 2, "marked_events": 1}
    assert client.delete(f"/cities/{belgrade}").status_code == 204

    assert [c["id"] for c in client.get("/cities").json()] == [london["id"]]
    assert client.get("/settings").json()["active_city_id"] == london["id"]
    assert client.get("/sources").json() == []
    assert client.get(f"/events/{first}").status_code == 404
    assert client.get(f"/cities/{belgrade}/contents").status_code == 404


def test_deleting_the_last_city_leaves_the_app_empty(client):
    city = client.post("/cities", json=LONDON).json()
    assert client.delete(f"/cities/{city['id']}").status_code == 204
    assert client.get("/settings").json()["active_city_id"] is None
    assert client.get("/sources").status_code == 409


def test_a_city_is_not_deleted_while_a_refresh_runs(client, monkeypatch):
    city = client.post("/cities", json=LONDON).json()
    container = client.app.state.container
    monkeypatch.setattr(container.refresh.progress, "stage", Stage.READING)
    busy = client.delete(f"/cities/{city['id']}")
    assert busy.status_code == 409 and "refresh" in busy.json()["detail"]


def test_the_map_link_names_the_city_unless_the_address_does(client):
    client.post("/cities", json={**LONDON, "card_language": "русский"})
    by_address, by_venue, with_city = seeded(
        client,
        ("a", raw_event("A", "2099-01-02", address="10 Downing Street")),
        ("a", raw_event("B", "2099-01-02", venue="The Old Vic")),
        ("a", raw_event("C", "2099-01-02", address="221B Baker Street, London NW1")),
    )

    def query(event_id):
        return client.get(f"/events/{event_id}").json()["map_url"].split("query=")[1]

    assert query(by_address) == "10+Downing+Street%2C+London%2C+United+Kingdom"
    assert query(by_venue) == "The+Old+Vic%2C+London%2C+United+Kingdom"
    assert query(with_city) == "221B+Baker+Street%2C+London+NW1"
    feed = client.get("/events", params={"start": "2099-01-01", "end": "2099-01-07"}).json()
    assert {o["event"]["map_url"] for o in feed} == {client.get(f"/events/{i}").json()["map_url"] for i in (by_address, by_venue, with_city)}
    assert "city_label" not in feed[0]["event"]


def test_the_fallback_tag_can_be_renamed_and_cards_built_again_keep_the_new_name(client):
    a, b = seeded(client, ("a", raw_event("Что-то", "2099-01-02", tags=["Другое"])), ("b", raw_event("Что-то", "2099-01-02", tags=["Другое"])))
    fallback = client.get("/tags").json()[-1]
    renamed = client.patch(f"/tags/{fallback['id']}", json={"name": "Прочее"}).json()
    assert renamed == {**fallback, "name": "Прочее"}
    assert client.get(f"/events/{a}").json()["tags"] == ["Прочее"]
    merged = client.post(f"/events/{a}/merge", json={"other_event_id": b}).json()
    assert merged["tags"] == ["Прочее"]


def test_a_tag_of_a_name_already_there_is_refused(client):
    client.post("/cities", json=LONDON)
    duplicate = client.post("/tags", json={"name": "concert"})
    assert duplicate.status_code == 409 and "concert" in duplicate.json()["detail"]
