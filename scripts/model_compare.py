"""Re-reads posts that are already stored in one data folder with another model into a fresh folder.

No Telegram traffic: only the given posts are copied, then extraction and merging run on them.
Usage: model_compare.py <source data dir> <target data dir> <model> <post id>...
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from where_to_go.container import Container
from where_to_go.db import Database
from where_to_go.domain import CollectedPost
from where_to_go.extraction import ExtractionContext
from where_to_go.llm import ClaudeJsonLlm
from where_to_go.repositories import PostRepository, SettingsRepository, SourceRepository, TagRepository


class CountingLlm:
    def __init__(self, inner) -> None:
        self._inner, self.calls = inner, 0

    async def complete_json(self, system, prompt, schema):
        self.calls += 1
        return await self._inner.complete_json(system, prompt, schema)


async def main(source_dir: Path, target_dir: Path, model: str, post_ids: list[int]) -> None:
    origin = Database(source_dir / "where-to-go.sqlite3")
    old_posts, old_sources = PostRepository(origin), SourceRepository(origin)
    extraction, matching = CountingLlm(ClaudeJsonLlm(model)), CountingLlm(ClaudeJsonLlm(model))
    c = Container.build(target_dir, extraction_llm=extraction, matching_llm=matching)
    city = c.cities.add("Белград", "Europe/Belgrade")
    c.settings.update(active_city_id=city.id)
    new_source_ids: dict[int, int] = {}
    for post_id in post_ids:
        post = old_posts.get(post_id)
        if post.source_id not in new_source_ids:
            old = old_sources.get(post.source_id)
            new_source_ids[post.source_id] = c.sources.add(city.id, old.kind, old.handle, old.title).id
        c.posts.add_new(
            new_source_ids[post.source_id],
            CollectedPost(post.external_id, post.url, post.published_at, post.text),
            list(post.image_paths),
        )
    sources = {s.id: s for s in c.sources.in_city(city.id)}
    posts = c.posts.unprocessed(list(sources))
    tags = c.tags.all()
    context = ExtractionContext(city, "русский", [t.name for t in tags if not t.is_fallback], TagRepository.FALLBACK)
    extractor = c.refresh._extractor
    for batch in extractor.batches(posts):
        for result in await extractor.extract(batch, sources, context):
            for index, event in enumerate(result.events):
                c.mentions.add(result.post_id, index, event)
            for place in result.places:
                c.places.add(city.id, result.post_id, place)
            c.posts.mark_processed(result.post_id)
    touched = await c.refresh._linker.link(city.id, c.mentions.unassigned())
    print(f"posts={len(posts)} extraction_calls={extraction.calls} matching_calls={matching.calls} cards={len(touched)}")
    await c.close()


asyncio.run(main(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], [int(a) for a in sys.argv[4:]]))
