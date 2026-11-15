"""Reading any website with an event afisha: its sitemap, the schema.org Event on its pages, their text.

Nothing here knows a particular site: sites describe their events for search engines in one standard way.
"""

from __future__ import annotations

import gzip
import logging
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from where_to_go.telegram import HtmlText, SourceError

_SITEMAP_LINE = re.compile(r"^\s*sitemap\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
_GZIP_MAGIC = b"\x1f\x8b"
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}")

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebEvent:
    """An event as a page describes it in its schema.org markup."""

    name: str
    start: datetime | date
    end: datetime | date | None
    start_raw: str
    place: str | None
    address: str | None
    locality: str | None
    description: str
    image: str | None
    price: str | None
    organizer: str | None


class PlainText:
    """A description as sites write it — HTML or Markdown — as plain text, the way Telegram posts are kept."""

    _TAG = re.compile(r"<[a-z][^>]*>", re.IGNORECASE)
    _RULES = (
        (re.compile(r"!\[[^\]]*\]\([^)]*\)"), ""),
        (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)"), r"\1 (\2)"),
        (re.compile(r"^#{1,6}\s*", re.MULTILINE), ""),
        (re.compile(r"(\*\*|__)(.+?)\1"), r"\2"),
        (re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])"), r"\1"),
        (re.compile(r"[ \t]+$", re.MULTILINE), ""),
    )

    @classmethod
    def of(cls, raw: str) -> str:
        text = raw
        if cls._TAG.search(text):
            body = HTMLParser(f"<body>{text}</body>").body
            text = HtmlText.extract(body) if body is not None else text
            text = re.sub(r"\n(?!\n)", "\n\n", text) if "\n\n" not in text else text
        for pattern, replacement in cls._RULES:
            text = pattern.sub(replacement, text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


class EventMarkup:
    """The first schema.org Event (or a subtype such as MusicEvent) in the page's JSON-LD blocks."""

    @classmethod
    def read(cls, html: str) -> WebEvent | None:
        for block in HTMLParser(html).css('script[type="application/ld+json"]'):
            try:
                data = json.loads(block.text(deep=True) or "null")
            except json.JSONDecodeError:
                continue
            for item in cls._items(data):
                event = cls._event(item)
                if event is not None:
                    return event
        return None

    @classmethod
    def _items(cls, data: Any) -> Iterator[dict[str, Any]]:
        if isinstance(data, list):
            for item in data:
                yield from cls._items(item)
        elif isinstance(data, dict):
            yield data
            for nested in ("@graph", "mainEntity"):
                if nested in data:
                    yield from cls._items(data[nested])

    @staticmethod
    def _is_event(item: dict[str, Any]) -> bool:
        kinds = item.get("@type")
        kinds = kinds if isinstance(kinds, list) else [kinds]
        return any(isinstance(k, str) and k.endswith("Event") for k in kinds)

    @classmethod
    def _event(cls, item: dict[str, Any]) -> WebEvent | None:
        if not cls._is_event(item):
            return None
        name = _text(item.get("name"))
        start_raw = _text(item.get("startDate"))
        start = _moment(start_raw)
        if not name or start is None:
            return None
        location = _first(item.get("location"))
        location = location if isinstance(location, dict) else {}
        address = location.get("address")
        address = address if isinstance(address, dict) else {"streetAddress": address}
        organizer = _first(item.get("organizer"))
        return WebEvent(
            name=name,
            start=start,
            end=_moment(_text(item.get("endDate"))),
            start_raw=start_raw,
            place=_text(location.get("name")),
            address=_text(address.get("streetAddress")),
            locality=_text(address.get("addressLocality")),
            description=PlainText.of(_text(item.get("description")) or ""),
            image=cls._image(item.get("image")),
            price=cls._price(item.get("offers")),
            organizer=_text(organizer.get("name")) if isinstance(organizer, dict) else _text(organizer),
        )

    @staticmethod
    def _image(value: Any) -> str | None:
        value = _first(value)
        if isinstance(value, dict):
            value = value.get("url") or value.get("contentUrl")
        return _text(value)

    @staticmethod
    def _price(value: Any) -> str | None:
        offer = _first(value)
        if not isinstance(offer, dict):
            return None
        currency = _text(offer.get("priceCurrency")) or ""
        if offer.get("price") not in (None, ""):
            return f"{offer['price']} {currency}".strip()
        if offer.get("lowPrice") not in (None, ""):
            return f"от {offer['lowPrice']} {currency}".strip()
        return None


class EventClock:
    """Turns a page's start and end into the city's wall clock.

    Some sites label their local time as UTC («19:00Z» for an event at 19:00 in Belgrade): for them the hours
    are taken as written. Whether a site does so is decided once, when it is added, from what its pages show.
    """

    def __init__(self, times_are_local: bool, zone: ZoneInfo) -> None:
        self._local = times_are_local
        self._zone = zone

    @property
    def is_local(self) -> bool:
        return self._local

    def local(self, value: datetime | date) -> datetime | date:
        if not isinstance(value, datetime):
            return value
        if self._local or value.tzinfo is None:
            return value.replace(tzinfo=None)
        return value.astimezone(self._zone).replace(tzinfo=None)

    @staticmethod
    def detect(event: WebEvent, page_text: str, zone: ZoneInfo) -> bool | None:
        """True: the page shows the hours written in a UTC-labelled start; False: it shows them converted to the
        city's time; None: nothing to tell by (a real offset, no time, or the page shows both or neither)."""
        start = event.start
        if not isinstance(start, datetime) or start.utcoffset() != timedelta(0):
            return None
        written, converted = start.strftime("%H:%M"), start.astimezone(zone).strftime("%H:%M")
        if written == converted:
            return None
        shows_written, shows_converted = _mentions(page_text, written), _mentions(page_text, converted)
        if shows_written != shows_converted:
            return shows_written
        return None

    @staticmethod
    def decide(votes: list[bool | None]) -> bool:
        """Local only when some page says so and none says otherwise: by default the offset is believed."""
        return True in votes and False not in votes


def in_horizon(start: datetime | date, end: datetime | date | None, today: date, days: int) -> bool:
    """Whether the event runs at any moment between today and `days` days later."""
    first, last = _day(start), _day(end or start)
    return first <= today + timedelta(days=days) and last >= today


class WebEventText:
    """The facts of an event page as plain text: what Claude reads instead of the page."""

    SHORT_DESCRIPTION = 200
    PAGE_TEXT_LIMIT = 3000

    @classmethod
    def render(cls, event: WebEvent, clock: EventClock, page_text: str) -> str:
        place = ", ".join(dict.fromkeys(p for p in (event.place, event.address, event.locality) if p))
        lines = [
            event.name,
            f"Начало: {_when(clock.local(event.start))}",
            f"Конец: {_when(clock.local(event.end))}" if event.end else None,
            f"Место: {place}" if place else None,
            f"Цена: {event.price}" if event.price else None,
            f"Организатор: {event.organizer}" if event.organizer else None,
        ]
        body = event.description
        if len(body) < cls.SHORT_DESCRIPTION and page_text:
            body = f"{body}\n\n{page_text[: cls.PAGE_TEXT_LIMIT]}".strip()
        return "\n".join(line for line in lines if line is not None) + "\n\n" + body


class PageText:
    @staticmethod
    def main(html: str) -> str:
        """The readable text of the page's main part, cleaned like a Telegram post."""
        tree = HTMLParser(html)
        node = tree.css_first("main") or tree.css_first("article") or tree.body
        return HtmlText.extract(node) if node is not None else ""


class PageMeta:
    @staticmethod
    def site_name(html: str) -> str | None:
        node = HTMLParser(html).css_first('meta[property="og:site_name"]')
        return _text(node.attributes.get("content")) if node is not None else None


class SiteAddress:
    _DATED = re.compile(r"^\d+$")

    @classmethod
    def parse(cls, link: str) -> tuple[str, str]:
        """The site and its section: «https://x.club/ru/events/a» → («https://x.club», «/ru/events/»).
        Dated folders (/events/2026/11/a) are left out, or the section would end with its month."""
        text = link.strip()
        if "://" not in text and re.match(r"^[\w.-]+\.[a-z]{2,}/", text, re.IGNORECASE):
            text = "https://" + text
        parts = urlsplit(text)
        segments = [s for s in parts.path.split("/") if s]
        if parts.scheme not in ("http", "https") or not parts.netloc or not segments:
            raise SourceError("Это не похоже на ссылку на страницу события")
        folders = segments[:-1]
        while folders and cls._DATED.match(folders[-1]):
            folders.pop()
        if not folders:
            raise SourceError("По этой ссылке раздел событий не найти: пришлось бы читать весь сайт")
        return f"{parts.scheme}://{parts.netloc}", "/" + "".join(f"{s}/" for s in folders)


class SitemapReader:
    """The list of a site's pages it keeps for search engines."""

    MAX_NESTED = 50

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def locate(self, site: str) -> list[str]:
        robots = await self._get(f"{site}/robots.txt")
        if robots is not None:
            named = list(dict.fromkeys(_SITEMAP_LINE.findall(robots.decode(errors="replace"))))
            if named:
                return named
        if await self._get(f"{site}/sitemap.xml") is not None:
            return [f"{site}/sitemap.xml"]
        raise SourceError("На сайте нет списка страниц (sitemap)")

    async def urls(self, sitemap_urls: list[str]) -> list[str]:
        """Every page the sitemaps list. A sitemap the site names that cannot be read is an error;
        a nested one that cannot be read now is skipped, the others still count."""
        found: dict[str, None] = {}
        seen: set[str] = set()
        for url in sitemap_urls:
            await self._collect(url, found, seen, nested=False)
        return list(found)

    async def _collect(self, url: str, found: dict[str, None], seen: set[str], nested: bool) -> None:
        if url in seen or len(seen) > self.MAX_NESTED:
            return
        seen.add(url)
        content = await self._get(url)
        root = self._parse(content)
        if root is None:
            if nested:
                log.warning("nested sitemap %s skipped", url)
                return
            raise SourceError("Сайт не отдал список страниц (sitemap)")
        locations = [(el.text or "").strip() for el in root.iter() if el.tag.endswith("loc")]
        if root.tag.endswith("sitemapindex"):
            for inner in locations:
                await self._collect(inner, found, seen, nested=True)
        else:
            found.update((loc, None) for loc in locations if loc)

    @staticmethod
    def _parse(content: bytes | None) -> ElementTree.Element | None:
        if content is None:
            return None
        try:
            return ElementTree.fromstring(content)
        except ElementTree.ParseError:
            return None

    async def _get(self, url: str) -> bytes | None:
        try:
            response = await self._client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        content = response.content
        if not content.startswith(_GZIP_MAGIC):
            return content
        try:
            return gzip.decompress(content)
        except (OSError, EOFError):
            return None


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _text(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _mentions(text: str, hours: str) -> bool:
    hour, minute = hours.split(":")
    return re.search(rf"(?<!\d)0?{int(hour)}:{minute}(?!\d)", text) is not None


def _day(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


def _when(value: datetime | date) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if isinstance(value, datetime) else value.isoformat()


def _moment(raw: str | None) -> datetime | date | None:
    if not raw:
        return None
    try:
        if "T" not in raw:
            return date.fromisoformat(raw[:10]) if _DAY.match(raw) else datetime.strptime(raw[:8], "%Y%m%d").date()
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
