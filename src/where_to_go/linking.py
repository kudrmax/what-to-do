from __future__ import annotations

from where_to_go.domain import Mark, Mention
from where_to_go.matching import CandidateFinder, DuplicateJudge
from where_to_go.repositories import EventRepository, MentionRepository
from where_to_go.resolution import EventResolver


class EventCards:
    """Keeps every card in sync with the mentions it is built from."""

    def __init__(self, events: EventRepository, mentions: MentionRepository, resolver: EventResolver) -> None:
        self._events = events
        self._mentions = mentions
        self._resolver = resolver

    def create(self, city_id: int, mention: Mention, locked: bool = False) -> int:
        event_id = self._events.create(city_id, mention.data)
        self._mentions.assign(mention.id, event_id, locked)
        return event_id

    def holds_post(self, event_id: int, post_id: int) -> bool:
        return any(m.post_id == post_id for m in self._mentions.of_event(event_id))

    def assign(self, mention: Mention, event_id: int) -> None:
        self._mentions.assign(mention.id, event_id)

    def merge(self, target_id: int, other_id: int) -> None:
        """The user says two cards are one event; their decision is final."""
        if target_id == other_id:
            raise ValueError("cannot merge a card with itself")
        target, other = self._events.get(target_id), self._events.get(other_id)
        if target.city_id != other.city_id:
            raise ValueError("cards belong to different cities")
        for mention in self._mentions.of_event(other_id):
            self._mentions.assign(mention.id, target_id, locked=True)
        for mention in self._mentions.of_event(target_id):
            self._mentions.assign(mention.id, target_id, locked=True)
        if not target.mark.is_complete and other.mark != target.mark:
            self._events.set_mark(
                target_id,
                Mark(
                    interest=target.mark.interest or other.mark.interest,
                    plan=target.mark.plan or other.mark.plan,
                ),
            )
        self._events.delete(other_id)
        self.refresh(target_id)

    def split(self, event_id: int, mention_id: int) -> int:
        """Takes one source's mention out into a card of its own."""
        mentions = self._mentions.of_event(event_id)
        mention = next((m for m in mentions if m.id == mention_id), None)
        if mention is None:
            raise KeyError(mention_id)
        if len(mentions) < 2:
            raise ValueError("a card with one source cannot be split")
        city_id = self._events.get(event_id).city_id
        new_id = self.create(city_id, mention, locked=True)
        for rest in mentions:
            if rest.id != mention_id:
                self._mentions.assign(rest.id, event_id, locked=True)
        self.refresh(event_id)
        self.refresh(new_id)
        return new_id

    def refresh(self, event_id: int) -> None:
        mentions = self._mentions.of_event(event_id)
        if not mentions:
            self._events.delete(event_id)
            return
        current = self._events.get(event_id)
        self._events.save_resolved(self._resolver.resolve(event_id, current.city_id, mentions, current.mark))


class EventLinker:
    """Attaches newly extracted mentions to existing cards or opens new ones."""

    CHUNK = 15

    def __init__(self, finder: CandidateFinder, judge: DuplicateJudge, cards: EventCards) -> None:
        self._finder = finder
        self._judge = judge
        self._cards = cards

    async def link(self, city_id: int, mentions: list[Mention]) -> set[int]:
        touched: set[int] = set()
        ordered = sorted(mentions, key=lambda m: (m.data.start_date, m.published_at))
        try:
            for start in range(0, len(ordered), self.CHUNK):
                touched |= await self._link_chunk(city_id, ordered[start : start + self.CHUNK])
        finally:
            for event_id in touched:
                self._cards.refresh(event_id)
        return touched

    async def _link_chunk(self, city_id: int, chunk: list[Mention]) -> set[int]:
        candidates = {e.id: e for m in chunk for e in self._finder.find(city_id, m)}
        if not candidates and len(chunk) == 1:
            return {self._cards.create(city_id, chunk[0])}
        decisions = await self._judge.decide(chunk, list(candidates.values()))
        by_mention = {m.id: m for m in chunk}
        placed: dict[int, int] = {}
        touched: set[int] = set()
        for decision in decisions:
            mention = by_mention[decision.mention_id]
            target = decision.event_id
            if target is None and decision.same_as_mention_id in placed:
                target = placed[decision.same_as_mention_id]
            # Two items of one post are two events: a post never announces the same event twice.
            if target is not None and not self._cards.holds_post(target, mention.post_id):
                event_id = target
                self._cards.assign(mention, event_id)
            else:
                event_id = self._cards.create(city_id, mention)
            placed[mention.id] = event_id
            touched.add(event_id)
        return touched
