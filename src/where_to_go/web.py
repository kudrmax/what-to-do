"""Reading any website with an event afisha: its sitemap, the schema.org Event on its pages, their text.

Nothing here knows a particular site: sites describe their events for search engines in one standard way.
"""

from __future__ import annotations

import gzip
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser

from where_to_go.telegram import HtmlText, SourceError

_SITEMAP_LINE = re.compile(r"^\s*sitemap\s*:\s*(\S+)", re.IGNORECASE | re.MULTILINE)
_GZIP_MAGIC = b"\x1f\x8b"


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
            if "@graph" in data:
                yield from cls._items(data["@graph"])

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
            description=_text(item.get("description")) or "",
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
    @staticmethod
    def parse(link: str) -> tuple[str, str]:
        """The site and its section: «https://x.club/ru/events/a» → («https://x.club», «/ru/events/»)."""
        text = link.strip()
        if "://" not in text and re.match(r"^[\w.-]+\.[a-z]{2,}/", text, re.IGNORECASE):
            text = "https://" + text
        parts = urlsplit(text)
        segments = [s for s in parts.path.split("/") if s]
        if parts.scheme not in ("http", "https") or not parts.netloc or not segments:
            raise SourceError("Это не похоже на ссылку на страницу события")
        prefix = "/" + "".join(f"{s}/" for s in segments[:-1])
        return f"{parts.scheme}://{parts.netloc}", prefix


class SitemapReader:
    """The list of a site's pages it keeps for search engines."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def locate(self, site: str) -> str:
        robots = await self._get(f"{site}/robots.txt")
        if robots is not None:
            named = _SITEMAP_LINE.findall(robots.decode(errors="replace"))
            if named:
                return named[0]
        if await self._get(f"{site}/sitemap.xml") is not None:
            return f"{site}/sitemap.xml"
        raise SourceError("На сайте нет списка страниц (sitemap)")

    async def urls(self, sitemap_url: str) -> list[str]:
        found: dict[str, None] = {}
        await self._collect(sitemap_url, found, seen=set())
        return list(found)

    async def _collect(self, url: str, found: dict[str, None], seen: set[str]) -> None:
        if url in seen:
            return
        seen.add(url)
        content = await self._get(url)
        if content is None:
            raise SourceError("Сайт не отдал список страниц (sitemap)")
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as error:
            raise SourceError("Список страниц сайта (sitemap) не читается") from error
        locations = [(el.text or "").strip() for el in root.iter() if el.tag.endswith("loc")]
        if root.tag.endswith("sitemapindex"):
            for nested in locations:
                await self._collect(nested, found, seen)
        else:
            found.update((loc, None) for loc in locations if loc)

    async def _get(self, url: str) -> bytes | None:
        try:
            response = await self._client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            return None
        if response.status_code != 200:
            return None
        content = response.content
        return gzip.decompress(content) if content.startswith(_GZIP_MAGIC) else content


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _text(value: Any) -> str | None:
    if isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return None
    return value.strip() or None


def _moment(raw: str | None) -> datetime | date | None:
    if not raw:
        return None
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw)
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
