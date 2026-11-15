from datetime import UTC, datetime, timedelta

import pytest

from tests.helpers import raw_event

from where_to_go.container import Container
from where_to_go.models import CollectedPost, ExtractedEvent, Mention, Source, SourceKind, SourcePublic, WebPage, WebSite
from where_to_go.reading_rules import ReadingRules

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
async def app(tmp_path):
    container = Container.build(tmp_path)
    city = container.cities.add("Белград", "Europe/Belgrade")
    yield container, city
    await container.close()


def add_site(container, city, handle="site.test/ru/events/") -> Source:
    source = container.sources.add(Source(city_id=city.id, kind=SourceKind.WEB, handle=handle, title="Сайт"))
    container.web.add_site(WebSite(source_id=source.id, sitemap_url="https://site.test/sitemap.xml", prefix="https://site.test/ru/events/"))
    return source


def add_post(container, source, external_id=1, text="факты") -> int:
    container.posts.add_new(source.id, CollectedPost(external_id=external_id, url="https://site.test/ru/events/a", published_at=NOW, text=text), [])
    return next(p.id for p in container.posts.unprocessed([source.id]) if p.external_id == external_id)


async def test_web_source_url_is_its_section(app):
    container, city = app
    source = add_site(container, city)
    assert SourcePublic.model_validate(source, from_attributes=True).url == "https://site.test/ru/events/"


async def test_deleting_web_source_removes_its_site_and_pages(app):
    container, city = app
    source = add_site(container, city)
    container.web.save_page(WebPage(source_id=source.id, url="https://site.test/ru/events/a", is_event=False, found_at=NOW, checked_at=NOW))
    container.catalog.delete(source.id)
    with pytest.raises(KeyError):
        container.web.site(source.id)
    assert container.web.pages(source.id) == {}


async def test_web_posts_are_not_reread_by_recent_rule(app):
    container, city = app
    source = add_site(container, city)
    post_id = add_post(container, source)
    container.posts.mark_processed(post_id, "old rules")
    assert container.posts.to_read([source.id], ReadingRules.POSTS, 20) == []


async def test_changed_page_is_read_again(app):
    container, city = app
    source = add_site(container, city)
    post_id = add_post(container, source)
    container.posts.mark_processed(post_id, ReadingRules.POSTS)
    container.posts.replace_text(post_id, "новые факты")
    post = container.posts.get(post_id)
    assert (post.text, post.processed_at) == ("новые факты", None)


async def test_changed_page_is_not_reread_when_user_merged_it(app):
    container, city = app
    source = add_site(container, city)
    post_id = add_post(container, source)
    container.posts.mark_processed(post_id, ReadingRules.POSTS)
    with container.db.session() as s:
        s.add(Mention(post_id=post_id, item_index=0, data=ExtractedEvent.model_validate(raw_event("x", "2026-11-20")), locked=True))
        s.commit()
    container.posts.replace_text(post_id, "новые факты")
    assert container.posts.get(post_id).text == "факты"
