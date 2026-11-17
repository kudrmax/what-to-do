from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from where_to_go.instagram import InstagramName, InstagramPage, InstagramUrls
from where_to_go.telegram import SourceError

FIXTURES = Path(__file__).parent / "fixtures" / "instagram"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_profile_lists_twelve_posts_with_full_captions():
    p = InstagramPage(read("profile.html")).profile()
    assert p.title == "Esthetic Joys Embassy / EJE"
    assert len(p.posts) == 12
    first = next(x for x in p.posts if x.code == "DfXPH9KN62V")
    assert first.caption.startswith("November schedule is here")
    assert first.day == date(2026, 11, 5)
    assert first.image_url.startswith("https://")
    assert [h.title for h in p.highlights] == ["timetable", "food", "breakfast", "full menu", "press", "drinks", "NY 2026"]
    assert p.highlights[0].id == "18107063872994570"


def test_page_without_data_is_not_a_profile():
    assert InstagramPage(read("login_wall.html")).profile() is None


def test_post_page_gives_time_carousel_and_place():
    d = InstagramPage(read("post_carousel.html")).post()
    assert d.code == "DfmlSc4DQL_"
    assert d.published_at == datetime.fromtimestamp(1794403493, UTC)
    assert len(d.image_urls) == 3 and d.place == "EJE Belgrade" and d.video_urls == []


def test_reel_page_gives_video():
    assert len(InstagramPage(read("reel.html")).post().video_urls) == 1


def test_page_without_data_is_not_a_post():
    assert InstagramPage(read("login_wall.html")).post() is None


def test_highlight_gives_every_story():
    assert len(InstagramPage(read("highlight_food.html")).stories()) == 23
    [story] = InstagramPage(read("highlight_timetable.html")).stories()
    assert story.video_url and story.image_url


def test_active_stories_page_has_none():
    assert InstagramPage(read("stories_active.html")).stories() == []


def test_anonymous_visitor_is_recognised():
    assert InstagramPage(read("profile.html")).anonymous()


def _page_with_renditions(renditions: list[dict]) -> InstagramPage:
    import json

    post = {"taken_at": 1, "pk": 1, "code": "X", "caption": None, "video_versions": renditions, "display_uri": "https://i/x"}
    data = {"x": {"if_not_gated_logged_out": post}}
    return InstagramPage(f'<script type="application/json">{json.dumps(data)}</script>')


@pytest.mark.parametrize(
    "widths, expected",
    [([1080, 720, 360], 720), ([360, 240], 360), ([480, 1080], 480)],
)
def test_video_rendition_is_the_smallest_wide_enough_else_the_largest(widths, expected):
    page = _page_with_renditions([{"type": 101 + i, "width": w, "url": f"https://v/{w}"} for i, w in enumerate(widths)])
    assert page.post().video_urls == [f"https://v/{expected}"]


@pytest.mark.parametrize(
    "link", ["instagram.com/eje.belgrade", "https://www.instagram.com/eje.belgrade/?hl=en", "@eje.belgrade", "@EJE.Belgrade"]
)
def test_name_from_link(link):
    assert InstagramName.parse(link) == "eje.belgrade"


@pytest.mark.parametrize("link", ["https://example.com/eje", "instagram.com/p/DfmlSc4DQL_/", "instagram.com/", "@"])
def test_not_a_profile_link_is_rejected(link):
    with pytest.raises(SourceError, match="Instagram profile"):
        InstagramName.parse(link)


def test_link_detection():
    assert InstagramName.is_link("https://www.instagram.com/eje.belgrade/")
    assert InstagramName.is_link("instagram.com/eje.belgrade")
    assert not InstagramName.is_link("https://instagram.com/reel/Dfz-Qxkt44U/")
    assert not InstagramName.is_link("https://instagram.com/stories/eje/1/")
    assert not InstagramName.is_link("https://t.me/afisha")


def test_urls():
    assert InstagramUrls.profile("eje") == "https://www.instagram.com/eje/"
    assert InstagramUrls.post("abc") == "https://www.instagram.com/p/abc/"
    assert InstagramUrls.highlight("1") == "https://www.instagram.com/stories/highlights/1/"
    assert InstagramUrls.is_story(InstagramUrls.highlight("1"))
    assert not InstagramUrls.is_story(InstagramUrls.post("abc"))
