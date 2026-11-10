from __future__ import annotations

from where_to_go.linking import EventCards
from where_to_go.models import (
    ChannelLink,
    ChannelReference,
    City,
    Post,
    PotentialSourceOrigin,
    PotentialSourcePublic,
    Source,
    SourceKind,
)
from where_to_go.repositories import EventRepository, PotentialSourceRepository, SourceRepository
from where_to_go.telegram import SourceError, TelegramChannelReader, TelegramHandle


class DuplicateSourceError(SourceError):
    pass


class SourceCatalog:
    """Adding and removing channels, with what follows from it for the cards."""

    def __init__(self, sources: SourceRepository, events: EventRepository, cards: EventCards, reader: TelegramChannelReader) -> None:
        self._sources = sources
        self._events = events
        self._cards = cards
        self._reader = reader

    async def add(self, city: City, link: str, title: str | None) -> Source:
        handle = TelegramHandle.parse(link)
        if any(s.handle.lower() == handle.lower() for s in self._sources.in_city(city.id)):
            raise DuplicateSourceError("Этот канал уже добавлен")
        name = (title or "").strip() or await self._reader.title(handle)
        return self._sources.add(Source(city_id=city.id, kind=SourceKind.TELEGRAM, handle=handle, title=name))

    def delete(self, source_id: int) -> None:
        """The source's posts go with it; cards only it announced disappear, shared ones lose its post."""
        affected = self._events.ids_of_source(source_id)
        self._sources.delete(source_id)
        for event_id in affected:
            self._cards.refresh(event_id)


class PotentialSources:
    """Channels the posts point to that the user has not added yet: leads to look at, never added on their own."""

    BOT_SUFFIX = "bot"

    def __init__(self, potential: PotentialSourceRepository, sources: SourceRepository, catalog: SourceCatalog) -> None:
        self._potential = potential
        self._sources = sources
        self._catalog = catalog

    def note(self, city_id: int, post: Post, references: list[ChannelReference]) -> None:
        known = self._known_handles(city_id) | {post.source.handle.lower()}
        found: dict[str, tuple[str, ChannelLink]] = {}
        for reference in references:
            handle = self._handle(reference.handle)
            if handle is None or handle.lower() in known:
                continue
            if handle.lower() not in found or reference.via == ChannelLink.FORWARD:
                found[handle.lower()] = (handle, reference.via)
        self._potential.note(city_id, post.id, dict(found.values()))

    def in_city(self, city_id: int) -> list[PotentialSourcePublic]:
        """Most pointed to first; a channel the user has since added as a source is left out."""
        known = self._known_handles(city_id)
        result = []
        for found, links in self._potential.in_city(city_id):
            if found.handle.lower() in known or (not found.processed and not links):
                continue
            origins = [
                PotentialSourceOrigin(via=link.via, source_title=link.post.source.title, post_url=link.post.url, published_at=link.post.published_at)
                for link in links
            ]
            origins.sort(key=lambda o: o.published_at, reverse=True)
            result.append(PotentialSourcePublic(id=found.id, handle=found.handle, processed=found.processed, found_at=found.found_at, origins=origins))
        result.sort(key=lambda p: (len(p.origins), max((o.published_at for o in p.origins), default=p.found_at)), reverse=True)
        return result

    def mark(self, potential_id: int, processed: bool) -> None:
        self._potential.mark(potential_id, processed)

    async def adopt(self, city: City, potential_id: int) -> Source:
        """Adds the channel as a source and only then marks it processed: if adding fails, nothing changes."""
        found = self._potential.get(potential_id)
        if found.city_id != city.id:
            raise KeyError(potential_id)
        try:
            source = await self._catalog.add(city, found.handle, None)
        except DuplicateSourceError:
            source = next(s for s in self._sources.in_city(city.id) if s.handle.lower() == found.handle.lower())
        self._potential.mark(found.id, True)
        return source

    def _known_handles(self, city_id: int) -> set[str]:
        return {s.handle.lower() for s in self._sources.in_city(city_id)}

    @classmethod
    def _handle(cls, raw: str) -> str | None:
        try:
            handle = TelegramHandle.parse(raw)
        except SourceError:
            return None
        return None if handle.lower().endswith(cls.BOT_SUFFIX) else handle
