import asyncio
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from tests.helpers import add_city
from where_to_go.container import Container
from where_to_go.instagram import InstagramPage
from where_to_go.instagram_reader import InstagramReader, InstagramRefused, InstagramRequests
from where_to_go.models import CollectedPost, InstagramReading, InstagramUrls, Source, SourceKind
from where_to_go.source_types import InstagramSourceType
from where_to_go.telegram import SourceError

FIXTURES = Path(__file__).parent / "fixtures" / "instagram"
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
NAME = "eje.belgrade"
POST_PAGES = {"DfmlSc4DQL_": "post_carousel.html", "Dfz-Qxkt44U": "reel.html"}
HIGHLIGHT_PAGES = {"18107063872994570": "highlight_timetable.html", "17944160280052446": "highlight_food.html"}
PROFILE_POSTS = 12
BROWSER = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


PROFILE = InstagramPage(read("profile.html")).profile()
ALL_POSTS = {post.pk for post in PROFILE.posts}
STORIES = {story.pk: story for name in HIGHLIGHT_PAGES.values() for story in InstagramPage(read(name)).stories()}


class FakeClock:
    """Time that moves only when someone sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


class FakeInstagram:
    """Serves the saved pages and remembers every request it got."""

    def __init__(self, mock: respx.MockRouter, clock: FakeClock | None = None) -> None:
        self.clock = clock or FakeClock()
        self.requests: list[httpx.Request] = []
        self.started: list[float] = []
        self.highlights = dict(HIGHLIGHT_PAGES)
        self.profile = mock.get(url__regex=r"^https://www\.instagram\.com/[^/]+/$", name="profile").mock(
            side_effect=self._answer(lambda _: httpx.Response(200, text=read("profile.html"), headers={"set-cookie": "csrftoken=abc; Path=/"}))
        )
        self.post = mock.get(url__regex=r"^https://www\.instagram\.com/p/[^/]+/$", name="post").mock(
            side_effect=self._answer(lambda request: httpx.Response(200, text=self.post_page(self._part(request))))
        )
        self.highlight = mock.get(url__regex=r"^https://www\.instagram\.com/stories/highlights/\d+/$", name="highlight").mock(
            side_effect=self._answer(lambda request: httpx.Response(200, text=read(self.highlights.get(self._part(request), "highlight_timetable.html"))))
        )

    @staticmethod
    def post_page(code: str) -> str:
        """The saved page of the post, or a minimal one built from what the profile shows of it."""
        if code in POST_PAGES:
            return read(POST_PAGES[code])
        summary = next(p for p in PROFILE.posts if p.code == code)
        media = {"pk": str(summary.pk), "code": code, "taken_at": int(noon(summary.day).timestamp()), "display_uri": summary.image_url}
        return f'<script type="application/json">{json.dumps({"if_not_gated_logged_out": media})}</script>'

    def _answer(self, respond):
        def answer(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            self.started.append(self.clock())
            return respond(request)

        return answer

    @staticmethod
    def _part(request: httpx.Request) -> str:
        return request.url.path.rstrip("/").rsplit("/", 1)[-1]


@pytest.fixture
def instagram():
    with respx.mock(assert_all_called=False) as mock:
        yield FakeInstagram(mock)


@pytest.fixture
async def client():
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
        yield http


def reader(client: httpx.AsyncClient, clock: FakeClock) -> InstagramReader:
    return InstagramReader(InstagramRequests(client, sleep=clock.sleep, clock=clock))


async def test_first_collect_reads_every_post_and_only_fresh_stories(instagram, client):
    collected = await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)

    posts = [p for p in collected if p.external_id in ALL_POSTS]
    stories = [p for p in collected if p.external_id in STORIES]
    assert len(posts) == PROFILE_POSTS and all(p.read for p in posts)
    assert instagram.post.call_count == PROFILE_POSTS
    assert len(stories) == len(STORIES)
    assert {p.external_id for p in stories if p.read} == {pk for pk, s in STORIES.items() if NOW - s.published_at <= timedelta(days=30)}
    assert 0 < sum(p.read for p in stories) < len(stories)
    assert [p.published_at for p in collected] == sorted(p.published_at for p in collected)


async def test_post_page_gives_time_images_video_and_place(instagram, client):
    collected = await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(stories=False), NOW)

    carousel = next(p for p in collected if p.external_id == 4028070912406127359)
    assert carousel.url == "https://www.instagram.com/p/DfmlSc4DQL_/"
    assert carousel.published_at == datetime.fromtimestamp(1794403493, UTC)
    assert carousel.text.endswith("\n\nPlace: EJE Belgrade")
    assert len(carousel.image_urls) == 3 and carousel.video_urls == []
    reel = next(p for p in collected if p.external_id == 4031839923051400724)
    assert len(reel.video_urls) == 1


async def test_post_page_without_data_ends_the_reading_and_keeps_what_came_before(instagram, client):
    refused_code = PROFILE.posts[3].code
    instagram.post.side_effect = instagram._answer(
        lambda request: httpx.Response(200, text=read("login_wall.html") if instagram._part(request) == refused_code else instagram.post_page(instagram._part(request)))
    )

    with pytest.raises(InstagramRefused) as raised:
        await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)

    assert {p.external_id for p in raised.value.collected} == {p.pk for p in PROFILE.posts[:3]}
    assert instagram.post.call_count == 4 and instagram.highlight.call_count == 0


async def test_refused_highlight_ends_the_reading_and_keeps_what_came_before(instagram, client):
    refused_id = PROFILE.highlights[2].id
    instagram.highlight.side_effect = instagram._answer(
        lambda request: httpx.Response(429) if instagram._part(request) == refused_id else httpx.Response(200, text=read(HIGHLIGHT_PAGES.get(instagram._part(request), "highlight_timetable.html")))
    )

    with pytest.raises(InstagramRefused, match="will try again on the next refresh") as raised:
        await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)

    assert {p.external_id for p in raised.value.collected} == ALL_POSTS | set(STORIES)
    assert instagram.highlight.call_count == 3
    assert [p.published_at for p in raised.value.collected] == sorted(p.published_at for p in raised.value.collected)


async def test_post_page_is_requested_only_for_unknown_posts(instagram, client):
    unknown = {4032299590525378232, 4028070912406127359}
    collected = await reader(client, instagram.clock).collect(NAME, ALL_POSTS - unknown, InstagramReading(stories=False), NOW)

    assert {p.external_id for p in collected} == unknown
    assert instagram.post.call_count == len(unknown)


async def test_second_collect_with_everything_known_finds_nothing(instagram, client):
    collected = await reader(client, instagram.clock).collect(NAME, ALL_POSTS | set(STORIES), InstagramReading(), NOW)

    assert collected == []
    assert instagram.post.call_count == 0


async def test_story_in_two_highlights_is_collected_once(instagram, client):
    instagram.highlights["17974043804994139"] = "highlight_food.html"

    collected = await reader(client, instagram.clock).collect(NAME, ALL_POSTS, InstagramReading(), NOW)

    assert len(collected) == len({p.external_id for p in collected}) == len(STORIES)
    food = next(p for p in collected if p.external_id == 4029614209434391353)
    assert food.text == "Pinned story from the highlight «food»"
    assert food.url == InstagramUrls.highlight("17944160280052446")


async def test_stories_off_requests_no_highlight(instagram, client):
    collected = await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(stories=False), NOW)

    assert instagram.highlight.call_count == 0
    assert {p.external_id for p in collected} == ALL_POSTS


async def test_posts_off_requests_no_post_page_and_gives_no_posts(instagram, client):
    collected = await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(posts=False), NOW)

    assert instagram.post.call_count == 0
    assert instagram.highlight.call_count == len(PROFILE.highlights)
    assert {p.external_id for p in collected} == set(STORIES)


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(429, text="Please wait a few minutes"),
        httpx.Response(302, headers={"location": "https://www.instagram.com/accounts/login/"}),
        httpx.Response(200, text=read("login_wall.html")),
    ],
)
async def test_profile_without_its_data_is_a_refusal(instagram, client, answer, caplog):
    instagram.profile.side_effect = None
    instagram.profile.return_value = answer

    with caplog.at_level(logging.WARNING), pytest.raises(InstagramRefused, match="Instagram refused to show the profile; will try again on the next refresh"):
        await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)
    assert NAME in caplog.text


async def test_network_error_is_a_refusal(instagram, client):
    instagram.profile.side_effect = httpx.ConnectError("down")

    with pytest.raises(InstagramRefused):
        await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)


@pytest.mark.parametrize("status", [429, 200])
async def test_refusal_is_logged_with_status_headers_and_the_start_of_the_body(instagram, client, caplog, status):
    instagram.profile.side_effect = None
    instagram.profile.return_value = httpx.Response(status, text="x" * 5000, headers={"retry-after": "60"})

    with caplog.at_level(logging.WARNING), pytest.raises(InstagramRefused):
        await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)
    assert f"Instagram refused https://www.instagram.com/{NAME}/: {status}" in caplog.text and "retry-after" in caplog.text
    assert "x" * 2048 in caplog.text and "x" * 2049 not in caplog.text


async def test_network_error_in_preview_says_instagram_did_not_respond(instagram, client):
    instagram.profile.side_effect = httpx.ConnectError("down")

    with pytest.raises(SourceError, match="^Instagram didn't respond$"):
        await reader(client, instagram.clock).title(NAME)


async def test_refusal_in_preview_asks_to_try_later(instagram, client):
    instagram.profile.side_effect = None
    instagram.profile.return_value = httpx.Response(429)

    with pytest.raises(SourceError, match="^Instagram refused to show the profile; try again later$"):
        await reader(client, instagram.clock).title(NAME)


async def test_missing_profile_is_said_so(instagram, client, caplog):
    instagram.profile.side_effect = None
    instagram.profile.return_value = httpx.Response(404, text="Page not found")

    with caplog.at_level(logging.WARNING), pytest.raises(SourceError, match="This Instagram profile doesn't exist") as raised:
        await reader(client, instagram.clock).title(NAME)
    assert not isinstance(raised.value, InstagramRefused)
    assert "refused" not in caplog.text


async def test_private_profile_is_said_so(instagram, client):
    instagram.profile.side_effect = None
    instagram.profile.return_value = httpx.Response(
        200,
        text='<script type="application/json">{"data":{"xig_user_by_username":{"username":"closed","is_private":true}}}</script>',
    )

    with pytest.raises(SourceError, match="This Instagram profile is private"):
        await reader(client, instagram.clock).title(NAME)


async def test_title_gives_the_name_and_the_number_of_highlights(instagram, client):
    assert await reader(client, instagram.clock).title(NAME) == ("Esthetic Joys Embassy / EJE", 7)


async def test_sources_read_concurrently_share_one_pause(instagram, client):
    requests = InstagramRequests(client, sleep=instagram.clock.sleep, clock=instagram.clock)
    first, second = InstagramReader(requests), InstagramReader(requests)

    await asyncio.gather(
        first.collect(NAME, set(), InstagramReading(), NOW),
        second.collect("other.place", set(), InstagramReading(), NOW),
    )

    gaps = [later - earlier for earlier, later in zip(instagram.started, instagram.started[1:])]
    assert len(instagram.started) > 2 and min(gaps) >= 1.0


async def test_no_request_carries_a_cookie(instagram, client):
    await reader(client, instagram.clock).collect(NAME, set(), InstagramReading(), NOW)

    assert len(instagram.requests) > 1
    assert [r for r in instagram.requests if "cookie" in r.headers] == []
    assert len(client.cookies) == 0


async def test_requests_look_like_a_browser(instagram, client):
    await reader(client, instagram.clock).title(NAME)

    [request] = instagram.requests
    assert {name: request.headers[name] for name in BROWSER} == BROWSER


@pytest.fixture
async def app(tmp_path, instagram):
    container = Container.build(tmp_path)
    city = add_city(container, "Белград", "Europe/Belgrade")
    yield container, city
    await container.close()


def source_type(container: Container, client: httpx.AsyncClient, clock: FakeClock) -> InstagramSourceType:
    return InstagramSourceType(reader(client, clock), container.posts, container.instagram, lambda: NOW)


async def test_preview_shows_the_profile_name_and_its_highlights(app, instagram):
    container, city = app

    preview = await container.catalog.preview(city, "@eje.belgrade")

    assert (preview.kind, preview.title, preview.handle, preview.highlights) == (SourceKind.INSTAGRAM, "Esthetic Joys Embassy / EJE", NAME, 7)


async def test_added_profile_keeps_what_to_read(app, instagram):
    container, city = app

    source = await container.catalog.add(city, "https://www.instagram.com/eje.belgrade/", None, reading=InstagramReading(stories=False))

    assert (source.kind, source.handle, source.title) == (SourceKind.INSTAGRAM, NAME, "Esthetic Joys Embassy / EJE")
    assert container.instagram.reading(source.id) == InstagramReading(stories=False)


async def test_added_profile_reads_everything_by_default(app, instagram):
    container, city = app

    source = await container.catalog.add(city, "instagram.com/eje.belgrade", None)

    assert container.instagram.reading(source.id) == InstagramReading()


async def test_collect_follows_the_stored_reading_and_skips_stored_posts(app, instagram, client):
    container, city = app
    source = container.sources.add(Source(kind=SourceKind.INSTAGRAM, handle=NAME, title="EJE", city_id=city.id))
    container.instagram.add(source.id, InstagramReading(stories=False))
    stored = PROFILE.posts[0]
    container.posts.add_new(source.id, CollectedPost(external_id=stored.pk, url=InstagramUrls.post(stored.code), published_at=NOW, text=stored.caption), [])

    collected = await source_type(container, client, instagram.clock).collect(source, city)

    assert instagram.highlight.call_count == 0
    assert {p.external_id for p in collected} == ALL_POSTS - {stored.pk}
    assert instagram.post.call_count == PROFILE_POSTS - 1


def test_a_known_profile_is_caught_from_the_link_alone():
    assert InstagramSourceType(None, None, None).handle_of("https://www.instagram.com/EJE.Belgrade/") == NAME
