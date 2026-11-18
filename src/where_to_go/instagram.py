from __future__ import annotations

import base64
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from where_to_go.models import InstagramUrls
from where_to_go.telegram import SourceError

_NAME = re.compile(r"^[A-Za-z0-9_.]{1,30}$")
_PROFILE_LINK = re.compile(r"^(?:https?://)?(?:www\.)?instagram\.com/([^/?#]+)/?(?:[?#].*)?$", re.IGNORECASE)
_NOT_PROFILES = {"p", "reel", "reels", "stories", "explore", "tv", "accounts", "direct"}
_POST_DAY = re.compile(r" on ([A-Z][a-z]+ \d{1,2}, \d{4})")
_TAG_QUALITY = re.compile(r"\.(\d{3,4})\.")
_MIN_VIDEO_WIDTH = 480


class InstagramName:
    @classmethod
    def is_link(cls, link: str) -> bool:
        return cls._from_link(link) is not None

    @classmethod
    def parse(cls, link: str) -> str:
        text = link.strip()
        if text.startswith("@"):
            name = text[1:]
        elif "/" not in text:
            name = text
        else:
            name = cls._from_link(text)
        if name is None or not _NAME.match(name):
            raise SourceError("This doesn't look like a link to an Instagram profile")
        return name.lower()

    @staticmethod
    def _from_link(link: str) -> str | None:
        match = _PROFILE_LINK.match(link.strip())
        if match is None or match.group(1).lower() in _NOT_PROFILES or not _NAME.match(match.group(1)):
            return None
        return match.group(1)


@dataclass(frozen=True)
class PostSummary:
    pk: int
    code: str
    caption: str
    image_url: str | None
    is_video: bool
    day: date | None


@dataclass(frozen=True)
class Highlight:
    id: str
    title: str


@dataclass(frozen=True)
class ProfileSummary:
    title: str
    posts: list[PostSummary] = field(default_factory=list)
    highlights: list[Highlight] = field(default_factory=list)


@dataclass(frozen=True)
class PostDetails:
    pk: int
    code: str
    published_at: datetime
    caption: str
    image_urls: list[str]
    video_urls: list[str]
    video_covers: dict[str, str]
    place: str | None


@dataclass(frozen=True)
class Story:
    pk: int
    published_at: datetime
    image_url: str | None
    video_url: str | None


class InstagramPage:
    """Reads the data Instagram embeds in the HTML it serves to an anonymous visitor."""

    def __init__(self, html: str) -> None:
        self._html = html
        self._blocks: list[Any] | None = None

    def anonymous(self) -> bool:
        return '"USER_ID":"0"' in self._html

    def private(self) -> bool:
        return any(isinstance(part, dict) and part.get("is_private") is True for part in self._values("xig_user_by_username"))

    def profile(self) -> ProfileSummary | None:
        """The profile arrives split over several blocks: the name in one, the posts and highlights in another."""
        user: dict = {}
        for part in self._values("xig_user_by_username"):
            if isinstance(part, dict):
                user.update(part)
        if "polaris_ordered_timeline_connection" not in user:
            return None
        posts = [self._summary(node) for node in self._nodes(user["polaris_ordered_timeline_connection"])]
        highlights = [
            Highlight(id=str(node["id"]), title=node.get("title") or "")
            for node in self._nodes(user.get("lox_highlights_connection"))
            if node.get("id")
        ]
        return ProfileSummary(
            title=user.get("full_name") or user.get("username") or "",
            posts=[post for post in posts if post is not None],
            highlights=highlights,
        )

    def holds_highlight(self, highlight_id: str) -> bool:
        """The page carries the highlight's own data, even when the highlight has no stories left."""
        for connection in self._values("xdt_api__v1__feed__reels_media__connection"):
            for node in self._nodes(connection if isinstance(connection, dict) else None):
                if node.get("id") == f"highlight:{highlight_id}" and isinstance(node.get("items"), list):
                    return True
        return False

    def post(self) -> PostDetails | None:
        for media in self._values("if_not_gated_logged_out"):
            if isinstance(media, dict) and media.get("taken_at") and media.get("code"):
                return self._details(media)
        return None

    def stories(self) -> list[Story]:
        result: dict[int, Story] = {}
        for items in self._values("items"):
            for item in items if isinstance(items, list) else []:
                if isinstance(item, dict) and item.get("taken_at") and item.get("pk"):
                    result.setdefault(int(item["pk"]), self._story(item))
        return list(result.values())

    @staticmethod
    def _nodes(connection: Any) -> Iterator[dict]:
        for edge in (connection or {}).get("edges") or []:
            node = edge.get("node")
            if isinstance(node, dict):
                yield node

    @staticmethod
    def _summary(node: dict) -> PostSummary | None:
        if not node.get("pk") or not node.get("code"):
            return None
        day = _POST_DAY.search(node.get("accessibility_caption") or "")
        return PostSummary(
            pk=int(node["pk"]),
            code=node["code"],
            caption=(node.get("caption") or {}).get("text") or "",
            image_url=node.get("display_uri"),
            is_video=node.get("__typename") == "XIGPolarisVideoMedia",
            day=datetime.strptime(day.group(1), "%B %d, %Y").date() if day else None,
        )

    @classmethod
    def _details(cls, media: dict) -> PostDetails:
        parts = media.get("carousel_media") or [media]
        videos = [(cls._video_url(part["video_versions"]), part.get("display_uri")) for part in parts if part.get("video_versions")]
        return PostDetails(
            pk=int(media["pk"]),
            code=media["code"],
            published_at=datetime.fromtimestamp(media["taken_at"], UTC),
            caption=(media.get("caption") or {}).get("text") or "",
            image_urls=[part["display_uri"] for part in parts if part.get("display_uri")],
            video_urls=[url for url, _ in videos if url],
            video_covers={url: cover for url, cover in videos if url and cover},
            place=(media.get("location") or {}).get("name"),
        )

    @classmethod
    def _story(cls, item: dict) -> Story:
        candidates = (item.get("image_versions2") or {}).get("candidates") or []
        return Story(
            pk=int(item["pk"]),
            published_at=datetime.fromtimestamp(int(item["taken_at"]), UTC),
            image_url=max(candidates, key=lambda candidate: candidate.get("width") or 0)["url"] if candidates else None,
            video_url=cls._video_url(item.get("video_versions") or []),
        )

    @classmethod
    def _video_url(cls, renditions: list[dict]) -> str | None:
        """The smallest rendition that is at least 480 px wide, else the largest one."""
        sized = [(cls._width(rendition), rendition["url"]) for rendition in renditions if rendition.get("url")]
        if not sized:
            return None
        wide_enough = [entry for entry in sized if entry[0] >= _MIN_VIDEO_WIDTH]
        return min(wide_enough, key=lambda entry: entry[0])[1] if wide_enough else max(sized, key=lambda entry: entry[0])[1]

    @staticmethod
    def _width(rendition: dict) -> int:
        """Renditions carry no width field; the signed URL names the encoding ("...C3.720.dash...") instead."""
        if rendition.get("width"):
            return int(rendition["width"])
        encoded = parse_qs(urlparse(rendition["url"]).query).get("efg", [""])[0]
        try:
            meta = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        except ValueError:
            return 0
        match = _TAG_QUALITY.search(str(meta.get("vencode_tag", ""))) if isinstance(meta, dict) else None
        return int(match.group(1)) if match else 0

    def _values(self, key: str) -> Iterator[Any]:
        for block in self._json_blocks():
            yield from self._find(block, key)

    @classmethod
    def _find(cls, node: Any, key: str) -> Iterator[Any]:
        if isinstance(node, dict):
            for name, value in node.items():
                if name == key:
                    yield value
                yield from cls._find(value, key)
        elif isinstance(node, list):
            for value in node:
                yield from cls._find(value, key)

    def _json_blocks(self) -> list[Any]:
        if self._blocks is None:
            self._blocks = []
            for script in HTMLParser(self._html).css('script[type="application/json"]'):
                try:
                    self._blocks.append(json.loads(script.text()))
                except ValueError:
                    continue
        return self._blocks
