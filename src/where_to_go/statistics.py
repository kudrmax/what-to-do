from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Field, col, select

from where_to_go.db import Database
from where_to_go.models import INTEREST_MAX, City, Event, Mention, PhotoText, Place, Plan, Post, Public, Source

WEEKS_SHOWN = 12


class PhotoStats(Public):
    total: int = Field(description="Photos in the city's posts")
    read: int = Field(description="Photos Claude has read")
    with_text: int = Field(description="Read photos that have any text on them")


class PostStats(Public):
    read: int = Field(description="Posts Claude has read")
    with_events: int = Field(description="Read posts that announce at least one event")


class EventStats(Public):
    announcements: int = Field(description="Events as single posts announced them, duplicates included")
    cards: int = Field(description="Cards after merging the same event announced several times")
    merged: int = Field(description="Cards built from more than one post")
    cancelled: int
    places: int = Field(description="Places without a date found in posts")


class PlanCount(Public):
    plan: Plan | None = Field(description="null: the card has no plan yet")
    count: int


class InterestCount(Public):
    interest: int | None = Field(description="Stars from 1 to 5; null: not rated")
    count: int


class TagCount(Public):
    tag: str
    count: int


class SourceStats(Public):
    id: int
    title: str
    posts: int
    events: int


class WeekStats(Public):
    start: date = Field(description="Monday of the week, in the city's time zone")
    posts: int = Field(description="Posts published that week and read")
    posts_with_events: int


class CityStats(Public):
    posts: PostStats
    photos: PhotoStats
    events: EventStats
    marked: int = Field(description="Cards with an interest or a plan")
    plans: list[PlanCount] = Field(description="Every plan, then no plan; zero counts included")
    interests: list[InterestCount] = Field(description="Stars 5 to 1, then not rated; zero counts included")
    tags: list[TagCount] = Field(description="Tags on cards, most used first")
    sources: list[SourceStats] = Field(description="Sources by the cards they contribute to, most first")
    weeks: list[WeekStats] = Field(description=f"From the week of the first post, at most {WEEKS_SHOWN} weeks, up to the current one; oldest first")


class Statistics:
    """Counts what the app has read, found and what the user marked, for one city."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def of_city(self, city: City, now: datetime | None = None) -> CityStats:
        zone = ZoneInfo(city.timezone)
        with self._db.session() as s:
            sources = list(s.exec(select(Source).where(Source.city_id == city.id)))
            source_ids = [source.id for source in sources]
            posts = [p for p in s.exec(select(Post).where(col(Post.source_id).in_(source_ids))) if p.processed_at is not None]
            mentions = list(s.exec(select(Mention).join(Post).where(col(Post.source_id).in_(source_ids))))
            events = list(s.exec(select(Event).where(Event.city_id == city.id)))
            places = len(list(s.exec(select(Place.id).where(Place.city_id == city.id))))
            images = [image for post in posts for image in post.image_paths]
            photo_texts = list(s.exec(select(PhotoText).where(col(PhotoText.image).in_(images))))

        posts_with_events = {m.post_id for m in mentions}
        mentions_per_event = Counter(m.event_id for m in mentions if m.event_id is not None)
        return CityStats(
            posts=PostStats(read=len(posts), with_events=sum(p.id in posts_with_events for p in posts)),
            photos=PhotoStats(total=len(images), read=len(photo_texts), with_text=sum(bool(t.text.strip()) for t in photo_texts)),
            events=EventStats(
                announcements=len(mentions),
                cards=len(events),
                merged=sum(mentions_per_event[e.id] > 1 for e in events),
                cancelled=sum(e.is_cancelled for e in events),
                places=places,
            ),
            marked=sum(e.interest is not None or e.plan is not None for e in events),
            plans=self._plans(events),
            interests=self._interests(events),
            tags=[TagCount(tag=tag, count=n) for tag, n in Counter(t for e in events for t in e.tags).most_common()],
            sources=self._sources(sources, posts, events),
            weeks=self._weeks(posts, posts_with_events, zone, now or datetime.now(zone)),
        )

    @staticmethod
    def _plans(events: list[Event]) -> list[PlanCount]:
        counts = Counter(e.plan for e in events)
        return [PlanCount(plan=plan, count=counts[plan]) for plan in [*Plan, None]]

    @staticmethod
    def _interests(events: list[Event]) -> list[InterestCount]:
        counts = Counter(e.interest for e in events)
        return [InterestCount(interest=stars, count=counts[stars]) for stars in [*range(INTEREST_MAX, 0, -1), None]]

    @staticmethod
    def _sources(sources: list[Source], posts: list[Post], events: list[Event]) -> list[SourceStats]:
        posts_of = Counter(p.source_id for p in posts)
        events_of = Counter(source_id for e in events for source_id in set(e.source_ids))
        rows = [SourceStats(id=s.id, title=s.title, posts=posts_of[s.id], events=events_of[s.id]) for s in sources]
        return sorted(rows, key=lambda row: (-row.events, -row.posts, row.title))

    @staticmethod
    def _weeks(posts: list[Post], posts_with_events: set[int], zone: ZoneInfo, now: datetime) -> list[WeekStats]:
        def monday(moment: datetime) -> date:
            day = moment.astimezone(zone).date()
            return day - timedelta(days=day.weekday())

        read, with_events = Counter[date](), Counter[date]()
        for post in posts:
            week = monday(post.published_at.replace(tzinfo=post.published_at.tzinfo or UTC))
            read[week] += 1
            with_events[week] += post.id in posts_with_events
        current = monday(now)
        first = max(min(read, default=current), current - timedelta(weeks=WEEKS_SHOWN - 1))
        starts = [first + timedelta(weeks=n) for n in range((current - first).days // 7 + 1)]
        return [WeekStats(start=start, posts=read[start], posts_with_events=with_events[start]) for start in starts]
