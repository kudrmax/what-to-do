"""Re-reads posts already stored in one data folder with another model, into a fresh folder. Spends Claude calls.

No Telegram traffic: only the given posts are copied, then reading and merging run on them.
Usage: model_compare.py <source data dir> <target data dir> <model> <post id>...
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from common import TEST_CITY
from where_to_go.container import Container
from where_to_go.llm import ClaudeJsonLlm
from where_to_go.models import CollectedPost, Source


class CountingLlm:
    def __init__(self, inner) -> None:
        self._inner, self.calls = inner, 0

    async def complete_json(self, system, prompt, schema, images=()):
        self.calls += 1
        return await self._inner.complete_json(system, prompt, schema, images)


async def main(source_dir: Path, target_dir: Path, model: str, post_ids: list[int]) -> None:
    origin = Container.build(source_dir)
    photos, extraction, matching = (CountingLlm(ClaudeJsonLlm(lambda: model)) for _ in range(3))
    c = Container.build(target_dir, extraction_llm=extraction, matching_llm=matching, photo_llm=photos)
    city = c.cities.active() or c.cities.add(*TEST_CITY)
    copies: dict[int, Source] = {}
    for post_id in post_ids:
        post = origin.posts.get(post_id)
        if post.source_id not in copies:
            old = origin.sources.get(post.source_id)
            copies[post.source_id] = c.sources.add(Source(city_id=city.id, handle=old.handle, title=old.title))
        collected = CollectedPost.model_validate(post, from_attributes=True)
        c.posts.add_new(copies[post.source_id].id, collected, post.image_paths)
    sources = {s.id: s for s in copies.values()}
    unread = c.posts.unprocessed(sources)
    for batch in c.photos.batches(c.photos.untranscribed(unread)):
        await c.photos.transcribe(batch)
    context = c.post_reader.context(city)
    for batch in c.post_reader.batches(unread):
        await c.post_reader.read(batch, sources, context)
    touched = await c.linker.link(city.id, c.mentions.unassigned(sources))
    print(f"photo_calls={photos.calls} extraction_calls={extraction.calls} matching_calls={matching.calls} cards={len(touched)}")
    await c.close()
    await origin.close()


asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], [int(a) for a in sys.argv[4:]]))
