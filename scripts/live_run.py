"""Runs a whole refresh against real channels into a data folder. Spends Claude calls: run only when agreed.

Usage: live_run.py <data dir> [channel ...]
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from common import BELGRADE_CHANNELS, TEST_CITY
from where_to_go.container import Container


async def main(data: Path, channels: list[str]) -> None:
    c = Container.build(data)
    city = c.cities.active() or c.cities.add(*TEST_CITY)
    known = {s.handle for s in c.sources.in_city(city.id)}
    for link in channels:
        if link.lstrip("@") not in known:
            await c.catalog.add(city, link, None)
    started = time.monotonic()
    c.refresh.start()
    while c.refresh.progress.running:
        p = c.refresh.progress
        print(f"[{time.monotonic() - started:5.0f}s] {p.stage} new={p.new_posts} read={p.posts_read}/{p.posts_to_read}", flush=True)
        await asyncio.sleep(15)
    p = await c.refresh.wait()
    print(p.model_dump_json(indent=1))
    await c.close()


asyncio.run(main(Path(sys.argv[1]), sys.argv[2:] or BELGRADE_CHANNELS))
