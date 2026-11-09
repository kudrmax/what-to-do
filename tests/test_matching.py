from datetime import date, time

import pytest

from tests.helpers import FakeLlm, mention
from where_to_go.db import Database
from where_to_go.models import EventFacts, EventKind
from where_to_go.matching import CandidateFinder, DuplicateJudge, MatchDecision
from where_to_go.repositories import CityRepository, EventRepository, SettingsRepository


def judge_answer(*decisions):
    return FakeLlm(lambda *_: {"decisions": [dict(zip(("announcement", "same_as_card", "same_as_announcement"), d)) for d in decisions]})


@pytest.fixture
def events():
    db = Database(":memory:")
    CityRepository(db, SettingsRepository(db)).add("Белград", "Europe/Belgrade")
    yield EventRepository(db)
    db.close()


def card(events, title, day, kind=EventKind.SINGLE, venue=None, end=None):
    facts = EventFacts(title=title, original_title=title, description="", kind=kind, start_date=day, end_date=end, venue=venue)
    return events.create(1, facts).id


async def test_judge_answers_are_validated(events):
    existing = events.get(card(events, "Кафаны", date(2026, 11, 13)))
    a, b, c, d = mention(1), mention(2), mention(3), mention(4)
    llm = judge_answer((1, 999, None), (2, existing.id, None), (3, None, 4), (4, None, 2))
    decisions = await DuplicateJudge(llm, lambda: "prompt").decide([a, b, c, d], [existing])
    assert decisions == [
        MatchDecision(1),  # unknown card id
        MatchDecision(2, event_id=existing.id),
        MatchDecision(3),  # points at a later announcement
        MatchDecision(4, same_as_mention_id=2),
    ]


async def test_missing_answer_means_a_new_event(events):
    assert await DuplicateJudge(judge_answer(), lambda: "prompt").decide([mention(1)], []) == [MatchDecision(1)]


def test_candidates_same_day_first_then_similar_titles_within_reschedule_window(events):
    same_day = card(events, "Джаз в подвале", date(2026, 11, 13))
    similar_later = card(events, "Лекция про кафаны", date(2026, 12, 20))
    unrelated_later = card(events, "Йога в парке", date(2026, 12, 20))
    far_away = card(events, "Лекция про кафаны", date(2027, 6, 1))
    found = [e.id for e in CandidateFinder(events).find(1, mention(9, title="Лекция про кафаны"))]
    assert found == [same_day, similar_later]
    assert unrelated_later not in found and far_away not in found


def test_running_exhibition_is_a_candidate_on_any_of_its_days(events):
    show = card(events, "Графика", date(2026, 11, 1), kind=EventKind.MULTIDAY, end=date(2026, 11, 30))
    assert [e.id for e in CandidateFinder(events).find(1, mention(9, day=date(2026, 11, 20), title="Другое"))] == [show]


async def test_the_judge_prompt_comes_from_settings(events):
    llm = judge_answer()
    await DuplicateJudge(llm, lambda: "мой промпт").decide([mention(1)], [])
    assert llm.calls[0][0] == "мой промпт"
