from __future__ import annotations

from urllib.parse import quote_plus

from where_to_go.api.schemas import (
    CityOut,
    ConflictOut,
    EventDetailOut,
    EventOut,
    MarkOut,
    MentionOut,
    RefreshOut,
    SourceOut,
    TagOut,
)
from where_to_go.container import Container
from where_to_go.domain import City, Event, Source, Tag
from where_to_go.refresh import RefreshProgress


class Presenter:
    """Turns domain objects into API responses."""

    def __init__(self, container: Container) -> None:
        self._c = container

    def city(self, city: City) -> CityOut:
        return CityOut(id=city.id, name=city.name, timezone=city.timezone, active=city.id == self._c.settings.active_city_id())

    @staticmethod
    def source(source: Source) -> SourceOut:
        return SourceOut(
            id=source.id,
            city_id=source.city_id,
            kind=source.kind,
            title=source.title,
            url=source.url,
            last_refreshed_at=source.last_refreshed_at,
            last_error=source.last_error,
            events_found=source.events_found,
        )

    @staticmethod
    def tag(tag: Tag) -> TagOut:
        return TagOut(id=tag.id, name=tag.name, is_fallback=tag.is_fallback)

    @staticmethod
    def event(event: Event) -> EventOut:
        place = event.address or event.venue
        return EventOut(
            id=event.id,
            kind=event.kind,
            title=event.title,
            original_title=event.original_title,
            description=event.description,
            start_date=event.start_date,
            end_date=event.end_date,
            start_time=event.start_time,
            recurrence=event.rrule,
            venue=event.venue,
            address=event.address,
            map_url=f"https://www.google.com/maps/search/?api=1&query={quote_plus(place)}" if place else None,
            price=event.price,
            tags=list(event.tags),
            image_url=f"/images/{event.image_path}" if event.image_path else None,
            is_cancelled=event.is_cancelled,
            conflicts=[ConflictOut(field=c.field, values=list(c.values)) for c in event.conflicts],
            source_ids=list(event.source_ids),
            mark=MarkOut(interest=event.mark.interest, plan=event.mark.plan),
        )

    def event_detail(self, event: Event) -> EventDetailOut:
        mentions = []
        for mention in self._c.mentions.of_event(event.id):
            post = self._c.posts.get(mention.post_id)
            mentions.append(
                MentionOut(
                    id=mention.id,
                    source_id=mention.source_id,
                    source_title=self._c.sources.get(mention.source_id).title,
                    post_url=post.url,
                    published_at=post.published_at,
                    original_title=mention.data.original_title,
                    post_text=post.text,
                    from_organizer=mention.data.from_organizer,
                    update_kind=mention.data.update_kind,
                )
            )
        return EventDetailOut(**self.event(event).model_dump(), mentions=mentions)

    @staticmethod
    def refresh(progress: RefreshProgress) -> RefreshOut:
        return RefreshOut(
            stage=progress.stage,
            running=progress.running,
            started_at=progress.started_at,
            finished_at=progress.finished_at,
            new_posts=progress.new_posts,
            posts_to_read=progress.posts_to_read,
            posts_read=progress.posts_read,
            events_touched=progress.events_touched,
            errors=list(progress.errors),
        )
