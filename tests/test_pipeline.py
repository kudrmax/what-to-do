from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from tests.helpers import channel_page, extraction_by_text, judge_same_titles, raw_event
from where_to_go.container import Container
from where_to_go.domain import Mark, Plan, SourceKind
from where_to_go.refresh import Stage
from where_to_go.repositories import SettingsRepository

RECENT = (datetime.now(UTC) - timedelta(days=2)).isoformat()
LATER = (datetime.now(UTC) - timedelta(days=1)).isoformat()


@pytest.fixture
async def app(tmp_path):
    extraction = extraction_by_text(
        {
            "кафаны": [raw_event("Кафаны", "2026-11-13", "19:00", from_organizer=True)],
            "дайджест": [raw_event("Кафаны", "2026-11-13", "19:30"), raw_event("Джаз", "2026-11-14", None)],
            "реклама": [],
        }
    )
    judge = judge_same_titles()
    http = httpx.AsyncClient()
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge, http=http)
    city = container.cities.add("Белград", "Europe/Belgrade")
    container.settings.set(SettingsRepository.ACTIVE_CITY, str(city.id))
    container.sources.add(city.id, SourceKind.TELEGRAM, "kafana", "Кафана")
    container.sources.add(city.id, SourceKind.TELEGRAM, "afisha", "Афиша")
    yield container, extraction, judge
    await container.close()


def serve_channels(kafana_posts, afisha_posts):
    respx.get(url__startswith="https://cdn.test/").respond(200, content=b"img", headers={"content-type": "image/jpeg"})
    respx.get("https://t.me/s/kafana").respond(200, text=channel_page("kafana", kafana_posts))
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", afisha_posts))


@respx.mock
async def test_refresh_turns_posts_into_merged_cards(app):
    container, _, _ = app
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, LATER, "дайджест недели"), (8, LATER, "реклама курса")])

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE, progress.errors
    events = {e.original_title: e for e in container.events.in_city(1)}
    assert set(events) == {"Кафаны", "Джаз"}
    kafana = events["Кафаны"]
    assert len(kafana.source_ids) == 2
    assert kafana.start_time.strftime("%H:%M") == "19:00"  # the organizer wins over the afisha
    assert [c.field for c in kafana.conflicts] == ["start_time"]
    assert kafana.image_path is not None
    assert {s.title: s.events_found for s in container.sources.in_city(1)} == {"Кафана": 1, "Афиша": 2}


@respx.mock
async def test_second_refresh_reads_only_new_posts(app):
    container, extraction, _ = app
    serve_channels([(1, RECENT, "лекция про кафаны")], [])
    container.refresh.start()
    await container.refresh.wait()
    calls = len(extraction.calls)

    container.refresh.start()
    await container.refresh.wait()

    assert len(extraction.calls) == calls
    assert len(container.events.in_city(1)) == 1


@respx.mock
async def test_unreachable_channel_is_recorded_on_the_source(app):
    container, _, _ = app
    respx.get("https://t.me/s/kafana").respond(302)
    respx.get("https://t.me/s/afisha").respond(200, text=channel_page("afisha", []))
    container.refresh.start()
    progress = await container.refresh.wait()
    kafana = next(s for s in container.sources.in_city(1) if s.handle == "kafana")
    assert "закрыт" in kafana.last_error
    assert progress.stage is Stage.DONE


@respx.mock
async def test_manual_split_and_merge_are_kept(app):
    container, _, _ = app
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, LATER, "дайджест недели")])
    container.refresh.start()
    await container.refresh.wait()
    kafana = next(e for e in container.events.in_city(1) if e.original_title == "Кафаны")
    container.events.set_mark(kafana.id, Mark(4, Plan.SURE))
    afisha_mention = next(m for m in container.mentions.of_event(kafana.id) if not m.data.from_organizer)

    split_id = container.cards.split(kafana.id, afisha_mention.id)

    assert len(container.events.get(kafana.id).source_ids) == 1
    assert all(m.locked for m in container.mentions.of_event(split_id))
    assert container.events.get(kafana.id).mark == Mark(4, Plan.SURE)

    container.cards.merge(kafana.id, split_id)

    assert len(container.events.get(kafana.id).source_ids) == 2
    with pytest.raises(KeyError):
        container.events.get(split_id)
