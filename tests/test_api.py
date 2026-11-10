import time

import pytest
import respx
from fastapi.testclient import TestClient

from tests.helpers import photos_saying, channel_page, extraction_by_text, judge_same_titles, raw_event
from where_to_go.api import create_app
from where_to_go.container import Container


@pytest.fixture
def client(tmp_path):
    extraction = extraction_by_text({"квиз": [raw_event("Квиз", "2099-01-02", "20:00", tags=["Игры и квизы"], photo=0)]})
    app = create_app(lambda: Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge_same_titles(), photo_llm=photos_saying()))
    with TestClient(app) as test_client:
        yield test_client


def test_empty_app_asks_for_a_city_first(client):
    assert client.get("/sources").status_code == 409
    assert client.get("/settings").json()["active_city_id"] is None


def test_first_city_becomes_active(client):
    city = client.post("/cities", json={"name": "Белград", "timezone": "Europe/Belgrade"}).json()
    assert client.get("/settings").json()["active_city_id"] == city["id"]
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
    assert (marked["interest"], marked["plan"], marked["is_going"]) == (2, "no", False)
    assert client.get("/events", params={"start": "2099-01-01", "end": "2099-01-07", "plans": "none"}).json() == []
    [mention] = client.get(f"/events/{event_id}/mentions").json()
    assert mention["post_url"] == "https://t.me/quizbg/3" and mention["source_title"] == "Канал quizbg"
    assert client.get("/sources").json()[0]["events_found"] == 1


def seeded(client, *events):
    """Puts cards straight into storage: one post and mention per (source handle, raw event)."""
    from datetime import UTC, datetime

    from where_to_go.models import CollectedPost, ExtractedEvent, Source

    c = client.app.state.container
    city = c.cities.active() or c.cities.add("Белград", "Europe/Belgrade")
    ids = []
    for handle, raw in events:
        source = next((s for s in c.sources.in_city(city.id) if s.handle == handle), None) or c.sources.add(Source(city_id=city.id, handle=handle, title=handle))
        external = len(c.posts.known_ids(source.id)) + 1
        c.posts.add_new(source.id, CollectedPost(external_id=external, url=f"https://t.me/{handle}/{external}", published_at=datetime(2026, 11, 1, tzinfo=UTC), text="текст"), [])
        post = next(p for p in c.posts.unprocessed([source.id]) if p.external_id == external)
        mention = c.mentions.add(post.id, 0, ExtractedEvent.model_validate(raw), None)
        c.posts.mark_processed(post.id, "test")
        ids.append(c.cards.create(city.id, mention))
        c.cards.refresh(ids[-1])
    return ids


def test_merge_and_split_through_the_api(client):
    a, b = seeded(client, ("kafana", raw_event("Кафаны", "2099-01-02", "19:00", from_organizer=True)), ("afisha", raw_event("Про кафаны", "2099-01-02", "19:30")))
    merged = client.post(f"/events/{a}/merge", json={"other_event_id": b}).json()
    mentions = client.get(f"/events/{a}/mentions").json()
    assert len(mentions) == 2 and merged["start_time"] == "19:00:00"
    assert merged["conflicts"] == [{"field": "start_time", "values": ["19:00", "19:30"]}]
    assert client.get(f"/events/{b}").status_code == 404
    assert client.post(f"/events/{a}/merge", json={"other_event_id": a}).status_code == 422

    afisha = next(m for m in mentions if not m["data"]["from_organizer"])
    split = client.post(f"/events/{a}/split", json={"mention_id": afisha["id"]}).json()
    assert split["id"] != a and [m["id"] for m in client.get(f"/events/{split['id']}/mentions").json()] == [afisha["id"]]
    assert client.post(f"/events/{a}/split", json={"mention_id": afisha["id"]}).status_code == 404
    [lone] = client.get(f"/events/{a}/mentions").json()
    assert client.post(f"/events/{a}/split", json={"mention_id": lone["id"]}).status_code == 422


def test_feed_filters(client):
    lecture, concert, untimed = seeded(
        client,
        ("a", raw_event("Лекция", "2099-01-02", "19:00")),
        ("b", raw_event("Концерт", "2099-01-02", "21:00", tags=["Концерт"])),
        ("a", raw_event("Что-то", "2099-01-03", None)),
    )
    window = {"start": "2099-01-01", "end": "2099-01-07"}

    def ids(**params):
        return [o["event"]["id"] for o in client.get("/events", params={**window, **params}).json()]

    assert ids() == [lecture, concert, untimed]
    assert ids(tags="Концерт") == [concert]
    b_source = next(s["id"] for s in client.get("/sources").json() if s["title"] == "b")
    assert ids(sources=b_source) == [concert]
    assert ids(only_timed=True) == [lecture, concert]
    client.put(f"/events/{concert}/mark", json={"interest": 5, "plan": "sure"})
    client.put(f"/events/{lecture}/mark", json={"interest": 1, "plan": "no"})
    assert ids(plans="none") == [untimed]
    assert ids() == [lecture, concert, untimed]
    assert ids(plans=["maybe", "sure"]) == [concert]
    past = client.get("/events", params={"end": "2099-01-02", "plans": "no"}).json()
    assert [o["event"]["id"] for o in past] == [lecture]
    assert client.put(f"/events/{concert}/mark", json={"interest": 9}).status_code == 422


def test_tags_settings_and_unknown_ids(client):
    client.post("/cities", json={"name": "Белград", "timezone": "Europe/Belgrade"})
    tags = client.get("/tags").json()
    assert tags[-1] == {"id": tags[-1]["id"], "name": "не распознано", "is_fallback": True}
    renamed_fallback = client.patch(f"/tags/{tags[-1]['id']}", json={"name": "Другое"})
    assert renamed_fallback.status_code == 422 and "не распознано" in renamed_fallback.json()["detail"]
    added = client.post("/tags", json={"name": "Танцы"}).json()
    assert client.get("/tags").json()[-2]["name"] == "Танцы"  # new tags go before the fallback
    assert client.patch(f"/tags/{added['id']}", json={"name": "Танцы и сальса"}).json()["name"] == "Танцы и сальса"
    assert client.patch("/tags/999", json={"name": "x"}).status_code == 404
    assert client.patch("/settings", json={"description_language": "английский"}).json()["description_language"] == "английский"
    assert client.get("/settings").json()["recent_posts"] == 20
    assert client.patch("/settings", json={"recent_posts": 5}).json()["recent_posts"] == 5
    too_small = client.patch("/settings", json={"recent_posts": 0})
    assert too_small.status_code == 422 and too_small.json() == {"detail": "Значение должно быть не меньше 1"}
    assert client.patch("/settings", json={"recent_posts": 301}).json() == {"detail": "Значение должно быть не больше 300"}
    assert client.patch("/settings", json={"active_city_id": 999}).status_code == 404
    assert client.get("/events/999").status_code == 404
    assert client.get("/images/../where-to-go.sqlite3").status_code == 404
    assert client.get("/settings/defaults").json()["recent_posts"] == 20
    bad_prompt = client.patch("/settings", json={"extraction_prompt": "Город {town}"})
    assert bad_prompt.status_code == 422 and "{town}" not in client.get("/settings").json()["extraction_prompt"]


def test_renaming_a_tag_renames_it_on_cards(client):
    [event_id] = seeded(client, ("a", raw_event("Концерт", "2099-01-02", tags=["Концерт"])))
    tag = next(t for t in client.get("/tags").json() if t["name"] == "Концерт")
    client.patch(f"/tags/{tag['id']}", json={"name": "Музыка"})
    assert client.get(f"/events/{event_id}").json()["tags"] == ["Музыка"]


def test_deleting_a_source_drops_cards_only_it_supported(client):
    only_a, shared, _ = seeded(
        client,
        ("a", raw_event("Только А", "2099-01-02")),
        ("a", raw_event("Общее", "2099-01-03")),
        ("b", raw_event("Общее", "2099-01-03")),
    )
    c = client.app.state.container
    shared_b = c.events.in_city(1)[-1].id
    client.post(f"/events/{shared}/merge", json={"other_event_id": shared_b})
    a_id = next(s["id"] for s in client.get("/sources").json() if s["title"] == "a")

    assert client.delete(f"/sources/{a_id}").status_code == 204

    assert client.get(f"/events/{only_a}").status_code == 404
    assert [m["source_title"] for m in client.get(f"/events/{shared}/mentions").json()] == ["b"]


@respx.mock
def test_closed_channel_cannot_be_added(client):
    respx.route(host="testserver").pass_through()
    respx.get("https://t.me/s/secretchan").respond(302)
    client.post("/cities", json={"name": "Белград", "timezone": "Europe/Belgrade"})
    response = client.post("/sources", json={"link": "t.me/secretchan"})
    assert response.status_code == 422 and "закрыт" in response.json()["detail"]
    assert client.post("/sources", json={"link": "https://example.com"}).status_code == 422


def calendar_entry(client, event_id):
    from icalendar import Calendar

    response = client.get(f"/events/{event_id}/calendar.ics")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/calendar")
    assert f'filename="event-{event_id}.ics"' in response.headers["content-disposition"]
    [entry] = Calendar.from_ical(response.content).walk("VEVENT")
    return entry, response.text


def test_calendar_file_of_a_timed_event(client):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    [quiz] = seeded(client, ("quizbg", raw_event("Квиз", "2099-01-02", "20:00", address="Улица 1")))
    entry, text = calendar_entry(client, quiz)
    start = datetime(2099, 1, 2, 20, 0, tzinfo=ZoneInfo("Europe/Belgrade"))
    assert entry.decoded("dtstart") == start and entry.decoded("dtend") == start + timedelta(hours=2)
    assert str(entry["summary"]) == "Квиз" and str(entry["location"]) == "Бар, Улица 1"
    assert str(entry["url"]) == "https://t.me/quizbg/1" and "Описание: Квиз" in str(entry["description"])
    assert "BEGIN:VTIMEZONE" in text and "TZID:Europe/Belgrade" in text


def test_calendar_file_of_untimed_multiday_and_recurring_events(client):
    from datetime import date

    untimed, fair, club = seeded(
        client,
        ("a", raw_event("Ярмарка", "2099-01-02", None)),
        ("a", raw_event("Выставка", "2099-01-02", "10:00", kind="multiday", end_date="2099-01-10")),
        ("a", raw_event("Клуб", "2099-01-05", "19:00", kind="recurring", rrule="FREQ=WEEKLY;BYDAY=TU")),
    )
    entry, _ = calendar_entry(client, untimed)
    assert (entry.decoded("dtstart"), entry.decoded("dtend")) == (date(2099, 1, 2), date(2099, 1, 3))
    entry, _ = calendar_entry(client, fair)
    assert (entry.decoded("dtstart"), entry.decoded("dtend")) == (date(2099, 1, 2), date(2099, 1, 11))
    entry, _ = calendar_entry(client, club)
    assert entry["rrule"]["FREQ"] == ["WEEKLY"] and entry["rrule"]["BYDAY"] == ["TU"]
    assert client.get("/events/999/calendar.ics").status_code == 404
