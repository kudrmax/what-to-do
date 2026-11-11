from datetime import UTC, date, datetime

from where_to_go.container import Container
from where_to_go.models import CollectedPost, EventFacts, EventKind, ExtractedEvent, Mark, PhotoText, Plan, Source
from where_to_go.repositories import PhotoTextRepository
from where_to_go.statistics import WEEKS_SHOWN

NOW = datetime(2026, 11, 11, 12, tzinfo=UTC)


def facts(title: str, tags: list[str]) -> EventFacts:
    return EventFacts(title=title, original_title=title, description="", kind=EventKind.SINGLE, start_date=date(2026, 11, 20), tags=tags)


def test_counts_what_the_city_gave(tmp_path):
    c = Container.build(tmp_path)
    city = c.cities.add("Белград", "Europe/Belgrade")
    other = c.cities.add("Нови-Сад", "Europe/Belgrade")
    bar = c.sources.add(Source(handle="bar", title="Бар", city_id=city.id))
    club = c.sources.add(Source(handle="club", title="Клуб", city_id=city.id))
    elsewhere = c.sources.add(Source(handle="ns", title="НС", city_id=other.id))

    def post(source, number, published, images=()):
        c.posts.add_new(source.id, CollectedPost(external_id=number, url=f"u{number}", published_at=published, text="т"), list(images))
        stored = next(p for p in c.posts.unprocessed([source.id]) if p.external_id == number)
        c.posts.mark_processed(stored.id, "rules")
        return stored

    first = post(bar, 1, datetime(2026, 11, 10, 9, tzinfo=UTC), ["a.jpg", "b.jpg", "c.jpg"])
    second = post(club, 2, datetime(2026, 11, 3, 9, tzinfo=UTC))
    post(club, 3, datetime(2026, 11, 4, 9, tzinfo=UTC))
    post(elsewhere, 4, datetime(2026, 11, 4, 9, tzinfo=UTC))
    c.posts.add_new(bar.id, CollectedPost(external_id=5, url="u5", published_at=NOW, text="unread"), [])
    PhotoTextRepository(c.db).save([PhotoText(image="a.jpg", text="Афиша", shows="poster", read_with="r"), PhotoText(image="b.jpg", text=" ", shows="people", read_with="r")])

    quiz = c.events.create(city.id, facts("Квиз", ["Игры и квизы"]))
    talk = c.events.create(city.id, facts("Лекция", ["Лекция", "Встреча"]))
    for index, (source_post, event) in enumerate([(first, quiz), (second, quiz), (first, talk)]):
        added = c.mentions.add(source_post.id, index, ExtractedEvent(**facts(event.title, event.tags).facts()), None)
        c.mentions.assign(added.id, event.id)
    quiz.source_ids, talk.source_ids = [bar.id, club.id], [bar.id]
    c.events.save(quiz)
    c.events.save(talk)
    c.events.set_mark(quiz.id, Mark(interest=5, plan=Plan.SURE))
    c.events.set_mark(talk.id, Mark(interest=2))

    stats = c.statistics.of_city(city, NOW)

    assert (stats.posts.read, stats.posts.with_events) == (3, 2)
    assert (stats.photos.total, stats.photos.read, stats.photos.with_text) == (3, 2, 1)
    assert (stats.events.announcements, stats.events.cards, stats.events.merged) == (3, 2, 1)
    assert stats.marked == 2
    assert {p.plan: p.count for p in stats.plans} == {Plan.MAYBE: 0, Plan.SURE: 1, Plan.NO: 0, Plan.WENT: 0, None: 1}
    assert [(i.interest, i.count) for i in stats.interests] == [(5, 1), (4, 0), (3, 0), (2, 1), (1, 0), (None, 0)]
    assert {t.tag: t.count for t in stats.tags} == {"Игры и квизы": 1, "Лекция": 1, "Встреча": 1}
    assert [(s.title, s.posts, s.events) for s in stats.sources] == [("Бар", 1, 2), ("Клуб", 2, 1)]
    assert [(w.start, w.posts, w.posts_with_events) for w in stats.weeks] == [(date(2026, 11, 2), 2, 1), (date(2026, 11, 9), 1, 1)]


def test_an_empty_city_has_zero_everywhere(tmp_path):
    c = Container.build(tmp_path)
    stats = c.statistics.of_city(c.cities.add("Белград", "Europe/Belgrade"), NOW)
    assert stats.posts.read == stats.events.cards == stats.marked == 0
    assert stats.tags == stats.sources == []
    assert [(w.start, w.posts) for w in stats.weeks] == [(date(2026, 11, 9), 0)]


def test_weeks_go_back_no_further_than_the_limit(tmp_path):
    c = Container.build(tmp_path)
    city = c.cities.add("Белград", "Europe/Belgrade")
    source = c.sources.add(Source(handle="bar", title="Бар", city_id=city.id))
    c.posts.add_new(source.id, CollectedPost(external_id=1, url="u", published_at=datetime(2025, 1, 1, tzinfo=UTC), text="т"), [])
    c.posts.mark_processed(c.posts.unprocessed([source.id])[0].id, "rules")
    weeks = c.statistics.of_city(city, NOW).weeks
    assert len(weeks) == WEEKS_SHOWN and weeks[-1].start == date(2026, 11, 9)
