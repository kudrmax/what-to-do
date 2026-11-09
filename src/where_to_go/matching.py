from __future__ import annotations

import json
from collections.abc import Callable
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlmodel import Field, SQLModel

from where_to_go.models import Event, EventFacts, Mention
from where_to_go.llm import JsonLlm, LlmError
from where_to_go.repositories import EventRepository

_WORD = re.compile(r"\w{3,}", re.UNICODE)


class TitleSimilarity:
    @staticmethod
    def words(*texts: str | None) -> set[str]:
        return {w.lower() for text in texts if text for w in _WORD.findall(text)}

    @classmethod
    def score(cls, mention: Mention, event: Event) -> float:
        a = cls.words(mention.data.title, mention.data.original_title, mention.data.venue)
        b = cls.words(event.title, event.original_title, event.venue)
        return len(a & b) / len(a | b) if a and b else 0.0


class CandidateFinder:
    """Cheap pre-filter: which existing cards could a new mention belong to."""

    SAME_DAY_SLACK = timedelta(days=1)
    RESCHEDULE_WINDOW = timedelta(days=120)
    MIN_SIMILARITY = 0.3
    LIMIT = 8

    def __init__(self, events: EventRepository) -> None:
        self._events = events

    def find(self, city_id: int, mention: Mention) -> list[Event]:
        day = mention.data.start_date
        same_days = self._events.near(city_id, day - self.SAME_DAY_SLACK, day + self.SAME_DAY_SLACK)
        wide = self._events.near(city_id, day - self.RESCHEDULE_WINDOW, day + self.RESCHEDULE_WINDOW)
        scored: dict[int, tuple[float, Event]] = {}
        for event in same_days:
            scored[event.id] = (1.0 + TitleSimilarity.score(mention, event), event)
        for event in wide:
            score = TitleSimilarity.score(mention, event)
            if score >= self.MIN_SIMILARITY and event.id not in scored:
                scored[event.id] = (score, event)
        ranked = sorted(scored.values(), key=lambda pair: pair[0], reverse=True)
        return [event for _, event in ranked[: self.LIMIT]]


class JudgeDecision(SQLModel):
    announcement: int = Field(description="Id of a new announcement")
    same_as_card: int | None = Field(default=None, description="Id of the existing card it describes, or null")
    same_as_announcement: int | None = Field(default=None, description="Id of an EARLIER new announcement it describes, or null")


class JudgeAnswer(SQLModel):
    decisions: list[JudgeDecision] = Field(description="One decision per new announcement")


@dataclass(frozen=True)
class MatchDecision:
    mention_id: int
    event_id: int | None = None
    same_as_mention_id: int | None = None


_FACTS_FOR_JUDGE = set(EventFacts.model_fields)


class DuplicateJudge:
    def __init__(self, llm: JsonLlm, prompt: Callable[[], str]) -> None:
        self._llm = llm
        self._prompt = prompt

    async def decide(self, mentions: list[Mention], candidates: list[Event]) -> list[MatchDecision]:
        prompt = json.dumps(
            {
                "existing_cards": [{"id": e.id, **self._facts(e)} for e in candidates],
                "new_announcements": [{"id": m.id, "update_kind": m.data.update_kind.value, **self._facts(m.data)} for m in mentions],
            },
            ensure_ascii=False,
            indent=1,
        )
        answer = await self._llm.complete_json(self._prompt(), prompt, JudgeAnswer.model_json_schema())
        try:
            decisions = JudgeAnswer.model_validate(answer)
        except ValidationError as error:
            raise LlmError(f"Claude answered in an unexpected shape: {error}") from error
        return self._validated(decisions, mentions, candidates)

    @staticmethod
    def _facts(facts: EventFacts) -> dict[str, Any]:
        return facts.model_dump(mode="json", include=_FACTS_FOR_JUDGE)

    @staticmethod
    def _validated(answer: JudgeAnswer, mentions: list[Mention], candidates: list[Event]) -> list[MatchDecision]:
        card_ids = {e.id for e in candidates}
        order = {m.id: i for i, m in enumerate(mentions)}
        given = {d.announcement: d for d in answer.decisions if d.announcement in order}
        decisions = []
        for mention in mentions:
            item = given.get(mention.id)
            card = item.same_as_card if item else None
            earlier = item.same_as_announcement if item else None
            if card in card_ids:
                decisions.append(MatchDecision(mention.id, event_id=card))
            elif earlier in order and order[earlier] < order[mention.id]:
                decisions.append(MatchDecision(mention.id, same_as_mention_id=earlier))
            else:
                decisions.append(MatchDecision(mention.id))
        return decisions
