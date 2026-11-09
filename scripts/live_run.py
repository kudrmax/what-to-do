"""Runs the whole pipeline once against real channels into a throwaway data folder."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from where_to_go.container import Container
from where_to_go.domain import SourceKind
from where_to_go.repositories import SettingsRepository
from where_to_go.telegram import TelegramHandle

CHANNELS = sys.argv[2:] or [
    "vstrechi_v_belgrade", "volna_srbjia", "afishabelgrad", "obitaniya_sreda", "F0RTHSP4CE", "standupbelgrade",
]


async def main(data: Path) -> None:
    c = Container.build(data)
    if not c.cities.all():
        city = c.cities.add("Белград", "Europe/Belgrade")
        c.settings.set(SettingsRepository.ACTIVE_CITY, str(city.id))
    city = c.cities.all()[0]
    known = {s.handle for s in c.sources.in_city(city.id)}
    for link in CHANNELS:
        handle = TelegramHandle.parse(link)
        if handle not in known:
            c.sources.add(city.id, SourceKind.TELEGRAM, handle, await c.reader.title(handle))
    started = time.monotonic()
    c.refresh.start()
    while c.refresh.progress.running:
        p = c.refresh.progress
        print(f"[{time.monotonic()-started:5.0f}s] {p.stage} new={p.new_posts} read={p.posts_read}/{p.posts_to_read}", flush=True)
        await asyncio.sleep(15)
    p = await c.refresh.wait()
    print("FINISHED", p.stage, f"{time.monotonic()-started:.0f}s", "new", p.new_posts, "read", p.posts_read, "touched", p.events_touched)
    for e in p.errors:
        print("ERROR", e)
    for s in c.sources.in_city(city.id):
        print("SOURCE", s.title, "|", s.events_found, "|", s.last_error)
    events = c.events.in_city(city.id)
    print("EVENTS", len(events), "multi-source", sum(1 for e in events if len(e.source_ids) > 1))
    await c.close()


asyncio.run(main(Path(sys.argv[1])))
