from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time
from typing import Any

from where_to_go.domain import EventKind, ExtractedEvent, Mention, UpdateKind


class FakeLlm:
    """Answers structured calls with a function of the prompt; records every call."""

    def __init__(self, answer: Callable[[str, str], dict[str, Any]]) -> None:
        self._answer = answer
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((system, prompt))
        return self._answer(system, prompt)


def extraction_by_text(events_by_marker: dict[str, list[dict[str, Any]]]) -> FakeLlm:
    """Extraction fake: a post whose text contains a marker yields the given raw events."""

    def answer(_: str, prompt: str) -> dict[str, Any]:
        posts = json.loads(prompt.split("\n", 1)[1])
        result = []
        for post in posts:
            events = next((e for marker, e in events_by_marker.items() if marker in post["text"]), [])
            result.append({"post_id": post["post_id"], "events": events, "places": []})
        return {"posts": result}

    return FakeLlm(answer)


def raw_event(title: str, day: str, at: str | None = "19:00", **extra: Any) -> dict[str, Any]:
    event = {
        "title": title,
        "original_title": title,
        "description": f"Описание: {title}",
        "kind": "single",
        "start_date": day,
        "end_date": None,
        "start_time": at,
        "rrule": None,
        "venue": "Бар",
        "address": None,
        "price": None,
        "tags": ["Лекция"],
        "update_kind": "announcement",
        "from_organizer": False,
        "image_index": None,
    }
    event.update(extra)
    return event


def judge_same_titles() -> FakeLlm:
    """Duplicate-judge fake: announcements with an equal original title are the same event."""

    def answer(_: str, prompt: str) -> dict[str, Any]:
        data = json.loads(prompt)
        decisions, seen = [], {}
        cards = {c["original_title"]: c["id"] for c in data["existing_cards"]}
        for item in data["new_announcements"]:
            key = item["original_title"]
            decisions.append(
                {"announcement": item["id"], "same_as_card": cards.get(key), "same_as_announcement": None if key in cards else seen.get(key)}
            )
            seen.setdefault(key, item["id"])
        return {"decisions": decisions}

    return FakeLlm(answer)


def mention(
    mention_id: int,
    *,
    day: date = date(2026, 11, 13),
    at: time | None = time(19, 0),
    published: datetime = datetime(2026, 11, 1, tzinfo=UTC),
    organizer: bool = False,
    update: UpdateKind = UpdateKind.ANNOUNCEMENT,
    source_id: int = 1,
    title: str = "Лекция",
    tags: tuple[str, ...] = ("Лекция",),
    price: str | None = None,
) -> Mention:
    return Mention(
        id=mention_id,
        post_id=mention_id,
        event_id=1,
        item_index=0,
        data=ExtractedEvent(
            title=title,
            original_title=title,
            description=f"{title} от {source_id}",
            kind=EventKind.SINGLE,
            start_date=day,
            start_time=at,
            price=price,
            tags=tags,
            update_kind=update,
            from_organizer=organizer,
        ),
        published_at=published,
        source_id=source_id,
        image_path=None,
    )


def channel_page(handle: str, posts: list[tuple[int, str, str]], before: int | None = None) -> str:
    """A minimal t.me/s/<handle> page; posts are (id, ISO datetime, text)."""
    items = "".join(
        f'<div class="tgme_widget_message_wrap"><div class="tgme_widget_message" data-post="{handle}/{pid}">'
        f'<a class="tgme_widget_message_photo_wrap" style="width:800px;background-image:url(\'https://cdn.test/{pid}.jpg\')"></a>'
        f'<div class="tgme_widget_message_text">{text}</div>'
        f'<a class="tgme_widget_message_date" href="https://t.me/{handle}/{pid}"><time datetime="{at}"></time></a>'
        "</div></div>"
        for pid, at, text in posts
    )
    more = f'<a class="tme_messages_more" data-before="{before}"></a>' if before else ""
    return (
        '<html><body><div class="tgme_channel_info"><div class="tgme_channel_info_header_title">'
        f"<span>Канал {handle}</span></div></div>{more}{items}</body></html>"
    )
