from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from tests.helpers import channel_page, extraction_by_text, judge_same_titles, raw_event
from where_to_go.container import Container
from where_to_go.domain import Mark, Plan, SourceKind
from where_to_go.llm import LlmError
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
    container.settings.update(active_city_id=city.id)
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


class FailingOnce:
    """Wraps a fake: the first `failures` calls raise like a Claude outage would."""

    def __init__(self, inner, failures: int = 1) -> None:
        self._inner, self._failures, self.calls = inner, failures, 0

    async def complete_json(self, system, prompt, schema):
        self.calls += 1
        if self.calls <= self._failures:
            raise LlmError("rate limited")
        return await self._inner.complete_json(system, prompt, schema)


async def build(tmp_path, extraction, judge):
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge, http=httpx.AsyncClient())
    city = container.cities.add("Белград", "Europe/Belgrade")
    container.settings.update(active_city_id=city.id)
    container.sources.add(city.id, SourceKind.TELEGRAM, "kafana", "Кафана")
    container.sources.add(city.id, SourceKind.TELEGRAM, "afisha", "Афиша")
    return container


@respx.mock
async def test_posts_claude_failed_to_read_are_retried_next_refresh(tmp_path):
    extraction = FailingOnce(extraction_by_text({"кафаны": [raw_event("Кафаны", "2026-11-13")]}))
    container = await build(tmp_path, extraction, judge_same_titles())
    serve_channels([(1, RECENT, "лекция про кафаны")], [])

    container.refresh.start()
    first = await container.refresh.wait()
    assert first.stage is Stage.DONE and any("не разобрал" in e for e in first.errors)
    assert container.events.in_city(1) == []

    container.refresh.start()
    await container.refresh.wait()
    assert [e.original_title for e in container.events.in_city(1)] == ["Кафаны"]
    await container.close()


@respx.mock
async def test_mentions_left_unmerged_by_a_failure_are_merged_next_refresh(tmp_path):
    extraction = extraction_by_text({"дайджест": [raw_event("Кафаны", "2026-11-13", "19:30")], "кафаны": [raw_event("Кафаны", "2026-11-13")]})
    judge = FailingOnce(judge_same_titles())
    container = await build(tmp_path, extraction, judge)
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, RECENT, "дайджест недели")])

    container.refresh.start()
    first = await container.refresh.wait()
    assert any("склеить" in e for e in first.errors)
    assert container.events.in_city(1) == []
    assert len(container.mentions.unassigned()) == 2

    container.refresh.start()
    await container.refresh.wait()
    [event] = container.events.in_city(1)
    assert len(container.mentions.of_event(event.id)) == 2
    await container.close()


@respx.mock
async def test_refresh_without_city_fails_visibly(tmp_path):
    container = Container.build(tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), http=httpx.AsyncClient())
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.stage is Stage.FAILED and "город" in progress.errors[0]
    await container.close()


@respx.mock
async def test_only_sources_of_the_active_city_are_refreshed(tmp_path):
    container = await build(tmp_path, extraction_by_text({}), judge_same_titles())
    other = container.cities.add("Бангкок", "Asia/Bangkok")
    container.sources.add(other.id, SourceKind.TELEGRAM, "bkk", "Бангкок афиша")
    serve_channels([], [])
    bangkok = respx.get("https://t.me/s/bkk").respond(200, text=channel_page("bkk", []))
    container.refresh.start()
    await container.refresh.wait()
    assert not bangkok.called
    await container.close()


@respx.mock
async def test_second_start_while_running_does_not_start_another(app):
    container, extraction, _ = app
    serve_channels([(1, RECENT, "лекция про кафаны")], [])
    first = container.refresh.start()
    second = container.refresh.start()
    assert first is second
    await container.refresh.wait()
    assert len(extraction.calls) == 1


@respx.mock
async def test_two_items_of_one_post_never_end_up_on_one_card(tmp_path):
    sessions = [raw_event("Speaking club", "2026-11-13", "13:00"), raw_event("Speaking club", "2026-11-13", "15:00")]
    container = await build(tmp_path, extraction_by_text({"дайджест": sessions, "клуб": [raw_event("Speaking club", "2026-11-13", "13:00")]}), judge_same_titles())
    serve_channels([], [(7, RECENT, "дайджест недели"), (8, LATER, "клуб в пятницу")])

    container.refresh.start()
    await container.refresh.wait()

    cards = container.events.in_city(1)
    assert sorted(len(container.mentions.of_event(e.id)) for e in cards) == [1, 2]
    assert all(e.conflicts == () for e in cards)
    await container.close()


@respx.mock
async def test_raising_recent_posts_reads_older_posts_of_a_channel_already_read(app):
    container, extraction, _ = app
    container.settings.update(recent_posts=2)
    serve_channels([(i, RECENT, f"пост {i}") for i in (1, 2, 3, 4)], [])
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.new_posts == 2
    kafana = next(s for s in container.sources.in_city(1) if s.handle == "kafana")
    assert kafana.last_post_id == 4

    container.settings.update(recent_posts=4)
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.new_posts == 2
    assert container.posts.known_ids(kafana.id) == {1, 2, 3, 4}


@respx.mock
async def test_digest_items_without_an_image_choice_get_no_image(tmp_path):
    digest = [raw_event("Квиз", "2026-11-13"), raw_event("Лекция", "2026-11-14")]
    single = [raw_event("Кафаны", "2026-11-15")]
    container = await build(tmp_path, extraction_by_text({"дайджест": digest, "кафаны": single}), judge_same_titles())
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, RECENT, "дайджест недели")])

    container.refresh.start()
    await container.refresh.wait()

    images = {e.original_title: e.image_path for e in container.events.in_city(1)}
    assert images["Квиз"] is None and images["Лекция"] is None
    assert images["Кафаны"] is not None
    await container.close()
