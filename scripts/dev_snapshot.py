"""Makes a data folder for frontend work from an already processed one, without calling Claude.

Mentions that were never merged get a card each, so every extracted event is visible.
Usage: dev_snapshot.py <processed data dir> <new data dir>
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from where_to_go.db import Database
from where_to_go.linking import EventCards
from where_to_go.repositories import EventRepository, MentionRepository, SettingsRepository, SourceRepository, TagRepository
from where_to_go.resolution import EventResolver

source, target = Path(sys.argv[1]), Path(sys.argv[2])
shutil.copytree(source, target)
db = Database(target / "where-to-go.sqlite3")
events, mentions = EventRepository(db), MentionRepository(db)
cards = EventCards(events, mentions, EventResolver(TagRepository.FALLBACK))
city_id = SettingsRepository(db).load().active_city_id
for mention in mentions.unassigned():
    cards.refresh(cards.create(city_id, mention))
for event in events.in_city(city_id):
    cards.refresh(event.id)
SourceRepository(db).recount_events()
print(len(events.in_city(city_id)), "cards")
