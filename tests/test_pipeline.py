import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from tests.helpers import photos_saying, FakeLlm, channel_page, extraction_by_text, judge_same_titles, raw_event
from where_to_go.container import Container
from where_to_go.models import Booking, BookingKind, Mark, Mention, Plan, Source
from where_to_go.llm import LlmError
from where_to_go.reading_rules import ReadingRules
from where_to_go.refresh import Stage
from where_to_go.repositories import SettingsRepository

RECENT = (datetime.now(UTC) - timedelta(days=2)).isoformat()
LATER = (datetime.now(UTC) - timedelta(days=1)).isoformat()


@pytest.fixture
async def app(tmp_path):
    extraction = extraction_by_text(
        {
            "кафаны": [raw_event("Кафаны", "2026-11-13", "19:00", from_organizer=True, photo=0)],
            "дайджест": [raw_event("Кафаны", "2026-11-13", "19:30"), raw_event("Джаз", "2026-11-14", None)],
            "реклама": [],
        }
    )
    judge = judge_same_titles()
    http = httpx.AsyncClient()
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge, photo_llm=photos_saying(), http=http)
    city = container.cities.add("Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
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
    container.events.set_mark(kafana.id, Mark(interest=4, plan=Plan.SURE))
    afisha_mention = next(m for m in container.mentions.of_event(kafana.id) if not m.data.from_organizer)

    split_id = container.cards.split(kafana.id, afisha_mention.id)

    assert len(container.events.get(kafana.id).source_ids) == 1
    assert all(m.locked for m in container.mentions.of_event(split_id))
    assert (container.events.get(kafana.id).interest, container.events.get(kafana.id).plan) == (4, Plan.SURE)

    container.cards.merge(kafana.id, split_id)

    assert len(container.events.get(kafana.id).source_ids) == 2
    with pytest.raises(KeyError):
        container.events.get(split_id)


class FailingOnce:
    """Wraps a fake: the first `failures` calls raise like a Claude outage would."""

    def __init__(self, inner, failures: int = 1) -> None:
        self._inner, self._failures, self.calls = inner, failures, 0

    async def complete_json(self, system, prompt, schema, images=()):
        self.calls += 1
        if self.calls <= self._failures:
            raise LlmError("rate limited")
        return await self._inner.complete_json(system, prompt, schema, images)


async def build(tmp_path, extraction, judge):
    container = Container.build(tmp_path, extraction_llm=extraction, matching_llm=judge, photo_llm=photos_saying(), http=httpx.AsyncClient())
    city = container.cities.add("Белград", "Europe/Belgrade")
    container.sources.add(Source(city_id=city.id, handle="kafana", title="Кафана"))
    container.sources.add(Source(city_id=city.id, handle="afisha", title="Афиша"))
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
    assert len(container.mentions.unassigned([1, 2])) == 2

    container.refresh.start()
    await container.refresh.wait()
    [event] = container.events.in_city(1)
    assert len(container.mentions.of_event(event.id)) == 2
    await container.close()


@respx.mock
async def test_refresh_without_city_fails_visibly(tmp_path):
    container = Container.build(tmp_path, extraction_llm=extraction_by_text({}), matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.stage is Stage.FAILED and "город" in progress.errors[0]
    await container.close()


@respx.mock
async def test_only_sources_of_the_active_city_are_refreshed(tmp_path):
    container = await build(tmp_path, extraction_by_text({}), judge_same_titles())
    other = container.cities.add("Бангкок", "Asia/Bangkok")
    container.sources.add(Source(city_id=other.id, handle="bkk", title="Бангкок афиша"))
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
    assert all(e.conflicts == [] for e in cards)
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
    assert container.posts.known_ids(kafana.id) == {3, 4}

    container.settings.update(recent_posts=4)
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.new_posts == 2
    assert container.posts.known_ids(kafana.id) == {1, 2, 3, 4}


@respx.mock
async def test_the_poster_of_a_digest_reaches_its_items_claude_gave_no_photo(tmp_path):
    digest = [raw_event("Квиз", "2026-11-13", photo=0), raw_event("Лекция", "2026-11-14", photo=None)]
    single = [raw_event("Кафаны", "2026-11-15", photo=0)]
    container = await build(tmp_path, extraction_by_text({"дайджест": digest, "кафаны": single}), judge_same_titles())
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, RECENT, "дайджест недели")])

    container.refresh.start()
    await container.refresh.wait()

    images = {e.original_title: e.image_path for e in container.events.in_city(1)}
    assert images["Квиз"] is not None and images["Лекция"] == images["Квиз"]
    assert images["Кафаны"] is not None
    await container.close()


SOON = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
LATER_DAY = (datetime.now(UTC) + timedelta(days=10)).date().isoformat()
EARLIER = (datetime.now(UTC) - timedelta(days=3)).isoformat()


@respx.mock
async def test_dateless_follow_ups_join_the_card_their_channel_announced(tmp_path):
    long_text = "Пьём тайваньские улуны из 500-летних деревьев в формате сухого заваривания, с вниманием к деталям и ощущениям."
    extraction = extraction_by_text(
        {
            "ивенты месяца": [raw_event("Церемония", SOON, "18:00", from_organizer=True), raw_event("Лекция", LATER_DAY, "18:00", from_organizer=True)],
            "зачем идти": [raw_event("Церемония", None, None, update_kind="details", description=long_text, from_organizer=True)],
            "не будет": [raw_event("Церемония", None, None, update_kind="cancellation", description="Отменена", from_organizer=True)],
            "про что-то": [raw_event("Мастер-класс", None, None, update_kind="details")],
            "афиша": [raw_event("Мастер-класс", LATER_DAY, "20:00")],
        }
    )
    container = await build(tmp_path, extraction, judge_same_titles())
    serve_channels(
        [(1, EARLIER, "ивенты месяца"), (2, RECENT, "зачем идти на церемонию"), (3, LATER, "церемонии не будет"), (4, LATER, "про что-то давнее")],
        [(7, RECENT, "афиша недели")],
    )

    container.refresh.start()
    progress = await container.refresh.wait()

    assert progress.stage is Stage.DONE, progress.errors
    cards = {(e.original_title, e.start_date.isoformat()): e for e in container.events.in_city(1)}
    assert set(cards) == {("Церемония", SOON), ("Лекция", LATER_DAY), ("Мастер-класс", LATER_DAY)}
    ceremony = cards[("Церемония", SOON)]
    assert ceremony.description == long_text and ceremony.is_cancelled
    assert ceremony.start_time.strftime("%H:%M") == "18:00" and ceremony.conflicts == []
    assert len(container.mentions.of_event(ceremony.id)) == 3
    # Only the afisha announced the workshop: the organizer's dateless note cannot be about it and is dropped.
    assert len(container.mentions.of_event(cards[("Мастер-класс", LATER_DAY)].id)) == 1
    assert container.mentions.unassigned(s.id for s in container.sources.in_city(1)) == []
    await container.close()


@respx.mock
async def test_a_dateless_follow_up_cannot_be_split_off(tmp_path):
    extraction = extraction_by_text(
        {"ивенты": [raw_event("Церемония", SOON, "18:00")], "зачем идти": [raw_event("Церемония", None, None, update_kind="details")]}
    )
    container = await build(tmp_path, extraction, judge_same_titles())
    serve_channels([(1, EARLIER, "ивенты"), (2, RECENT, "зачем идти")], [])
    container.refresh.start()
    await container.refresh.wait()

    [card] = container.events.in_city(1)
    follow_up = next(m for m in container.mentions.of_event(card.id) if m.data.is_dateless_follow_up)
    with pytest.raises(ValueError, match="нет даты"):
        container.cards.split(card.id, follow_up.id)
    await container.close()


async def refresh(container):
    container.refresh.start()
    progress = await container.refresh.wait()
    assert progress.stage is Stage.DONE, progress.errors
    return progress


@pytest.fixture
def new_rules(monkeypatch):
    return lambda: monkeypatch.setattr(ReadingRules, "POSTS", "next")


@respx.mock
async def test_an_edited_prompt_reads_no_post_again(tmp_path):
    container = await build(tmp_path, extraction_by_text({"дайджест": [raw_event("Квиз", SOON)]}), judge_same_titles())
    serve_channels([(1, RECENT, "дайджест месяца")], [])
    await refresh(container)

    container.settings.update(extraction_prompt=container.settings.load().extraction_prompt + "\nRead the photos too.")

    assert (await refresh(container)).posts_to_read == 0
    await container.close()


@respx.mock
async def test_cards_already_built_get_the_poster_their_post_shares(tmp_path):
    answers = {"цикл": [raw_event("Лекция 1", SOON, photo=0), raw_event("Лекция 2", LATER_DAY, photo=0)]}
    container = await build(tmp_path, extraction_by_text(answers), judge_same_titles())
    serve_channels([(1, RECENT, "цикл лекций")], [])
    await refresh(container)
    card = next(e for e in container.events.in_city(1) if e.original_title == "Лекция 2")
    [second] = container.mentions.of_event(card.id)
    with container.db.session() as s:
        stored = s.get(Mention, second.id)
        stored.image_index = None
        s.add(stored)
        s.commit()
    container.cards.refresh(second.event_id)
    assert container.events.get(second.event_id).image_path is None

    await refresh(container)

    images = {e.original_title: e.image_path for e in container.events.in_city(1)}
    assert images["Лекция 2"] is not None and images["Лекция 2"] == images["Лекция 1"]
    await container.close()


@respx.mock
async def test_posts_read_with_old_rules_are_read_again_and_keep_their_cards_and_marks(tmp_path, new_rules):
    answers = {
        "дайджест": [raw_event("Квиз", SOON, None, from_organizer=True), raw_event("Лекция", LATER_DAY, "19:00", from_organizer=True)],
        "реклама": [],
    }
    container = await build(tmp_path, extraction_by_text(answers), judge_same_titles())
    serve_channels([(1, EARLIER, "дайджест месяца"), (2, RECENT, "реклама")], [])
    await refresh(container)
    quiz = next(e for e in container.events.in_city(1) if e.original_title == "Квиз")
    container.events.set_mark(quiz.id, Mark(interest=5, plan=Plan.SURE))

    answers["дайджест"] = [
        raw_event("Квиз", SOON, "20:00", from_organizer=True, price=500, currency="RSD"),
        raw_event("Чайный клуб", LATER_DAY, "18:00", from_organizer=True),
    ]
    new_rules()
    progress = await refresh(container)

    assert progress.posts_to_read == 2
    cards = {e.original_title: e for e in container.events.in_city(1)}
    assert set(cards) == {"Квиз", "Чайный клуб"}  # the lecture is no longer announced, its card is gone
    again = cards["Квиз"]
    assert again.id == quiz.id and (again.interest, again.plan) == (5, Plan.SURE)
    assert again.start_time.strftime("%H:%M") == "20:00" and again.price == 500
    assert len(container.mentions.of_event(quiz.id)) == 1

    progress = await refresh(container)
    assert progress.posts_to_read == 0


@respx.mock
async def test_only_the_latest_posts_of_a_channel_and_not_hand_curated_ones_are_read_again(tmp_path, new_rules):
    answers = {marker: [raw_event(marker.title(), SOON, "19:00")] for marker in ("первый", "второй", "третий", "четвёртый")}
    container = await build(tmp_path, extraction_by_text(answers), judge_same_titles())
    container.settings.update(recent_posts=3)
    days_ago = [(datetime.now(UTC) - timedelta(days=d)).isoformat() for d in (4, 3, 2, 1)]
    serve_channels([(i + 1, day, text) for i, (day, text) in enumerate(zip(days_ago, ("первый", "второй", "третий", "четвёртый")))], [])
    container.settings.update(recent_posts=4)
    await refresh(container)
    container.settings.update(recent_posts=3)
    cards = {e.original_title: e.id for e in container.events.in_city(1)}
    container.cards.merge(cards["Третий"], cards["Четвёртый"])

    new_rules()
    progress = await refresh(container)

    assert progress.posts_to_read == 1  # post 2: post 1 is older than the latest three, 3 and 4 were merged by hand
    kafana = next(s for s in container.sources.in_city(1) if s.handle == "kafana")
    assert [p.external_id for p in container.posts.to_read([kafana.id], "other rules", 3)] == [2]


@respx.mock
async def test_places_of_a_post_read_again_are_not_doubled(tmp_path, new_rules):
    def answer(_, prompt):
        posts = json.loads(prompt.split("\n", 1)[1])
        return {"posts": [{"post_id": p["post_id"], "events": [], "places": [{"name": "Скалодром", "address": None, "description": "Каждый день"}]} for p in posts]}

    container = await build(tmp_path, FakeLlm(answer), judge_same_titles())
    serve_channels([(1, RECENT, "про скалодром")], [])
    await refresh(container)
    new_rules()
    await refresh(container)
    assert [p.name for p in container.places.in_city(1)] == ["Скалодром"]


class ProcessDied(BaseException):
    """The app stopped right here: nothing after this line runs, not even exception handlers."""


def die_on(target, method: str, monkeypatch) -> None:
    def died(*args, **kwargs):
        raise ProcessDied

    monkeypatch.setattr(target, method, died)


async def stop_midway(container) -> None:
    container.refresh.start()
    with pytest.raises(ProcessDied):
        await container.refresh.wait()
    await container.close()


async def finish_after_restart(tmp_path) -> Container:
    container = Container.build(tmp_path, extraction_llm=extraction_by_text(TWO_POSTS), matching_llm=judge_same_titles(), photo_llm=photos_saying(), http=httpx.AsyncClient())
    container.refresh.start()
    assert (await container.refresh.wait()).stage is Stage.DONE
    return container


TWO_POSTS = {"дайджест": [raw_event("Кафаны", "2026-11-13", "19:30")], "кафаны": [raw_event("Кафаны", "2026-11-13")]}


@respx.mock
async def test_a_stop_while_linking_leaves_no_card_without_posts_and_the_next_refresh_links_them(tmp_path, monkeypatch):
    container = await build(tmp_path, extraction_by_text(TWO_POSTS), judge_same_titles())
    serve_channels([(1, RECENT, "лекция про кафаны")], [(7, RECENT, "дайджест недели")])
    die_on(container.mentions, "assign", monkeypatch)
    await stop_midway(container)
    monkeypatch.undo()

    restarted = Container.build(tmp_path, http=httpx.AsyncClient())
    assert restarted.events.in_city(1) == []
    assert len(restarted.mentions.unassigned([1, 2])) == 2
    await restarted.close()

    container = await finish_after_restart(tmp_path)
    [event] = container.events.in_city(1)
    assert len(container.mentions.of_event(event.id)) == 2
    assert event.source_ids == [1, 2]
    await container.close()


@respx.mock
async def test_a_stop_while_storing_a_post_keeps_none_of_it_and_the_post_is_read_again(tmp_path, monkeypatch):
    container = await build(tmp_path, extraction_by_text(TWO_POSTS), judge_same_titles())
    serve_channels([(1, RECENT, "лекция про кафаны")], [])
    die_on(container.posts, "mark_processed", monkeypatch)
    await stop_midway(container)
    monkeypatch.undo()

    restarted = Container.build(tmp_path, http=httpx.AsyncClient())
    assert restarted.mentions.of_post(1) == []
    assert [p.id for p in restarted.posts.unprocessed([1])] == [1]
    await restarted.close()

    container = await finish_after_restart(tmp_path)
    [event] = container.events.in_city(1)
    assert len(container.mentions.of_post(1)) == 1 and event.source_ids == [1]
    await container.close()


def test_a_transaction_saves_everything_or_nothing(tmp_path):
    container = Container.build(tmp_path, extraction_llm=FakeLlm([]), matching_llm=FakeLlm([]), photo_llm=photos_saying(), http=httpx.AsyncClient())
    with pytest.raises(ProcessDied), container.db.transaction():
        container.cities.add("Белград", "Europe/Belgrade")
        raise ProcessDied
    assert container.cities.all() == []
    with container.db.transaction():
        container.cities.add("Белград", "Europe/Belgrade")
        container.cities.add("Нови-Сад", "Europe/Belgrade")
    assert len(Container.build(tmp_path, http=httpx.AsyncClient()).cities.all()) == 2


@respx.mock
async def test_a_card_keeps_where_to_sign_up_as_a_booking(tmp_path):
    booking = {"url": "https://t.me/reg_bot", "kind": "registration"}
    container = await build(tmp_path, extraction_by_text({"кафаны": [raw_event("Кафаны", SOON, booking=booking)]}), judge_same_titles())
    serve_channels([(1, RECENT, "лекция про кафаны")], [])

    await refresh(container)

    [card] = container.events.in_city(1)
    assert card.booking == Booking(url="https://t.me/reg_bot", kind=BookingKind.REGISTRATION)
    await container.close()
