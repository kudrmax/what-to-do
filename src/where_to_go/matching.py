from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from where_to_go.domain import Event, Mention
from where_to_go.llm import JsonLlm
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


@dataclass(frozen=True)
class MatchDecision:
    mention_id: int
    event_id: int | None = None
    same_as_mention_id: int | None = None


_DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decisions"],
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["announcement", "same_as_card", "same_as_announcement"],
                "properties": {
                    "announcement": {"type": "integer"},
                    "same_as_card": {"type": ["integer", "null"]},
                    "same_as_announcement": {"type": ["integer", "null"]},
                },
            },
        }
    },
}

_JUDGE_SYSTEM = """You merge duplicate event announcements collected from several Telegram channels.

You get existing event cards and new announcements. For every new announcement decide whether it describes the same real-world event as one of the existing cards, as one of the earlier new announcements, or neither.

Same event: the same happening at the same place on the same date, even when titles differ or are in different languages. Also the same: a post that reschedules, cancels or adds details to an event announced earlier (update_kind says so), and a single date of a recurring event that has a recurring card.
Not the same: different events at the same venue on the same day; the same show or tour on different dates; different sessions of a festival when each is its own event.

Answer for every new announcement. same_as_card is a card id or null; same_as_announcement is the id of an EARLIER new announcement in the list or null. Never set both."""


class DuplicateJudge:
    def __init__(self, llm: JsonLlm) -> None:
        self._llm = llm

    async def decide(self, mentions: list[Mention], candidates: list[Event]) -> list[MatchDecision]:
        prompt = json.dumps(
            {
                "existing_cards": [self._card(e) for e in candidates],
                "new_announcements": [self._announcement(m) for m in mentions],
            },
            ensure_ascii=False,
            indent=1,
        )
        answer = await self._llm.complete_json(_JUDGE_SYSTEM, prompt, _DECISION_SCHEMA)
        return self._validated(answer, mentions, candidates)

    @staticmethod
    def _validated(answer: dict[str, Any], mentions: list[Mention], candidates: list[Event]) -> list[MatchDecision]:
        card_ids = {e.id for e in candidates}
        order = {m.id: i for i, m in enumerate(mentions)}
        raw = {d["announcement"]: d for d in answer.get("decisions", []) if d.get("announcement") in order}
        decisions = []
        for mention in mentions:
            item = raw.get(mention.id, {})
            card = item.get("same_as_card")
            earlier = item.get("same_as_announcement")
            if card in card_ids:
                decisions.append(MatchDecision(mention.id, event_id=card))
            elif earlier in order and order[earlier] < order[mention.id]:
                decisions.append(MatchDecision(mention.id, same_as_mention_id=earlier))
            else:
                decisions.append(MatchDecision(mention.id))
        return decisions

    @staticmethod
    def _card(event: Event) -> dict[str, Any]:
        return {
            "id": event.id,
            "title": event.title,
            "original_title": event.original_title,
            "kind": event.kind.value,
            "date": event.start_date.isoformat(),
            "end_date": event.end_date.isoformat() if event.end_date else None,
            "recurrence": event.rrule,
            "time": event.start_time.strftime("%H:%M") if event.start_time else None,
            "venue": event.venue,
            "address": event.address,
            "description": event.description,
        }

    @staticmethod
    def _announcement(mention: Mention) -> dict[str, Any]:
        data = mention.data
        return {
            "id": mention.id,
            "title": data.title,
            "original_title": data.original_title,
            "kind": data.kind.value,
            "date": data.start_date.isoformat(),
            "end_date": data.end_date.isoformat() if data.end_date else None,
            "recurrence": data.rrule,
            "time": data.start_time.strftime("%H:%M") if data.start_time else None,
            "venue": data.venue,
            "address": data.address,
            "update_kind": data.update_kind.value,
            "description": data.description,
        }
