"""Prints every card of the active city with its sources, for eyeballing extraction and merging quality."""
from __future__ import annotations

import sys
from pathlib import Path

from where_to_go.db import Database
from where_to_go.repositories import EventRepository, MentionRepository, PostRepository, SettingsRepository, SourceRepository

db = Database(Path(sys.argv[1]) / "where-to-go.sqlite3")
events, mentions, posts, sources = EventRepository(db), MentionRepository(db), PostRepository(db), SourceRepository(db)
city_id = SettingsRepository(db).load().active_city_id
for event in events.in_city(city_id):
    when = f"{event.start_date}{'–' + str(event.end_date) if event.end_date else ''} {event.start_time or '??:??'}"
    flags = " ".join(f for f in [event.kind.value, "ОТМЕНА" if event.is_cancelled else "", event.rrule or ""] if f)
    print(f"#{event.id} {when} [{', '.join(event.tags)}] {event.title}  ({flags})")
    print(f"    {event.venue or '-'} | {event.address or '-'} | {event.price or '-'} | img={'yes' if event.image_path else 'no'}")
    print(f"    {event.description}")
    for conflict in event.conflicts:
        print(f"    КОНФЛИКТ {conflict.field}: {conflict.values}")
    for m in mentions.of_event(event.id):
        post = posts.get(m.post_id)
        print(f"    <- {sources.get(m.source_id).title} {post.url} org={m.data.from_organizer} {m.data.update_kind.value}: {m.data.original_title}")
