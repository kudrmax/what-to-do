from __future__ import annotations

from where_to_go.linking import EventCards
from where_to_go.models import City, Source, SourceKind
from where_to_go.repositories import EventRepository, SourceRepository
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
