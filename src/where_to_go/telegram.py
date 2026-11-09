from __future__ import annotations

import re
from datetime import datetime

import httpx
from selectolax.lexbor import LexborHTMLParser as HTMLParser, LexborNode as Node

from where_to_go.domain import CollectedPost

_HANDLE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")
_BACKGROUND_URL = re.compile(r"background-image:url\('([^']+)'\)")


class SourceError(Exception):
    """A problem the user should see next to the source."""


class TelegramHandle:
    @staticmethod
    def parse(link: str) -> str:
        text = link.strip()
        text = re.sub(r"^(https?://)?(www\.)?(t\.me|telegram\.me)/", "", text)
        text = re.sub(r"^s/", "", text)
        text = text.lstrip("@").split("/")[0].split("?")[0]
        if not _HANDLE.match(text):
            raise SourceError("Это не похоже на ссылку на публичный Telegram-канал")
        return text


class TelegramPageParser:
    """Reads the public web preview of a channel (t.me/s/<handle>)."""

    def __init__(self, html: str) -> None:
        self._tree = HTMLParser(html)

    def is_channel(self) -> bool:
        return self._tree.css_first(".tgme_channel_info") is not None

    def title(self) -> str | None:
        node = self._tree.css_first(".tgme_channel_info_header_title")
        return node.text(strip=True) if node else None

    def posts(self) -> list[CollectedPost]:
        result = []
        for node in self._tree.css(".tgme_widget_message[data-post]"):
            if "service_message" in (node.attributes.get("class") or ""):
                continue  # "pinned a photo" and the like: nothing to read
            post = self._post(node)
            if post is not None:
                result.append(post)
        return result

    def _post(self, node: Node) -> CollectedPost | None:
        ident = node.attributes.get("data-post") or ""
        _, _, number = ident.rpartition("/")
        time_node = node.css_first(".tgme_widget_message_date time")
        if not number.isdigit() or time_node is None:
            return None
        text_node = node.css_first(".tgme_widget_message_text")
        text = HtmlText.extract(text_node) if text_node else ""
        preview = node.css_first(".tgme_widget_message_link_preview")
        if preview is not None:
            text = (text + "\n\n" + HtmlText.extract(preview)).strip()
        images = []
        for photo in node.css(".tgme_widget_message_photo_wrap, .tgme_widget_message_video_thumb"):
            match = _BACKGROUND_URL.search(photo.attributes.get("style") or "")
            if match:
                images.append(match.group(1))
        if not text and not images:
            return None
        return CollectedPost(
            external_id=int(number),
            url=f"https://t.me/{ident}",
            published_at=datetime.fromisoformat(time_node.attributes["datetime"]),
            text=text,
            image_urls=tuple(images),
        )


class HtmlText:
    @staticmethod
    def extract(node: Node) -> str:
        parts: list[str] = []
        HtmlText._walk(node, parts)
        text = "".join(parts)
        text = re.sub(r"[ \t ]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def _walk(node: Node, parts: list[str]) -> None:
        child = node.child
        while child is not None:
            tag = child.tag
            if tag == "-text":
                parts.append(child.text_content or "")
            elif tag == "br":
                parts.append("\n")
            elif tag == "a":
                label = child.text(deep=True)
                href = child.attributes.get("href") or ""
                parts.append(label)
                if href.startswith("http") and href.rstrip("/") not in label:
                    parts.append(f" ({href})")
            elif tag in ("div", "p"):
                parts.append("\n")
                HtmlText._walk(child, parts)
                parts.append("\n")
            elif tag in ("script", "style"):
                pass
            else:
                HtmlText._walk(child, parts)
            child = child.next


class TelegramChannelReader:
    BASE = "https://t.me/s/"
    MAX_PAGES = 15

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def title(self, handle: str) -> str:
        parser = await self._page(handle, None)
        return parser.title() or handle

    async def new_posts(self, handle: str, known: set[int], recent: int) -> list[CollectedPost]:
        """Posts not read yet, oldest first: everything newer than what was read, and any of the latest
        `recent` posts that was not read (so raising `recent` reaches back into a channel already read)."""
        newest_known = max(known, default=None)
        seen: dict[int, CollectedPost] = {}
        before: int | None = None
        for _ in range(self.MAX_PAGES):
            page = (await self._page(handle, before)).posts()
            if not page:
                break
            seen.update((post.external_id, post) for post in page)
            oldest = min(post.external_id for post in page)
            if len(seen) >= recent and (newest_known is None or oldest <= newest_known):
                break
            before = oldest
        ordered = sorted(seen)
        wanted = set(ordered[-recent:]) | {i for i in ordered if newest_known is not None and i > newest_known}
        return [seen[i] for i in ordered if i in wanted and i not in known]

    async def _page(self, handle: str, before: int | None) -> TelegramPageParser:
        params = {"before": before} if before else None
        try:
            response = await self._client.get(self.BASE + handle, params=params, follow_redirects=False)
        except httpx.HTTPError as error:
            raise SourceError(f"Telegram не ответил: {error.__class__.__name__}") from error
        if response.status_code != 200:
            raise SourceError("Канал закрыт или у него выключен веб-просмотр")
        parser = TelegramPageParser(response.text)
        if not parser.is_channel():
            raise SourceError("Канал закрыт или у него выключен веб-просмотр")
        return parser

