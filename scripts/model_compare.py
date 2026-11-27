"""Re-reads posts already stored in one data folder with another reader, into a fresh folder. Spends Claude Code or
ChatGPT plan calls.

No Telegram traffic: only the given posts are copied, then reading and merging run on them.
Usage:
  model_compare.py <source data dir> <target data dir> <model> <post id>...
  model_compare.py --provider codex --model gpt-6.1-terra --effort low <source data dir> <target data dir> <post id>...
The first form reads with Claude Code; `--provider claude --model <model>` is the same.
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from where_to_go.settings import ClaudeModel, CodexEffort, CodexModel, LlmProvider


@dataclass(frozen=True)
class Comparison:
    source_dir: Path
    target_dir: Path
    provider: LlmProvider
    model: str
    effort: CodexEffort | None
    post_ids: list[int]

    @classmethod
    def parse(cls, argv: list[str]) -> Comparison:
        parser = argparse.ArgumentParser(prog="model_compare.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument("--provider", type=LlmProvider, choices=list(LlmProvider), default=None)
        parser.add_argument("--model")
        parser.add_argument("--effort", type=CodexEffort, choices=list(CodexEffort))
        parser.add_argument("source_dir", type=Path)
        parser.add_argument("target_dir", type=Path)
        parser.add_argument("rest", nargs="+", help="the model (positional form only), then the post ids")
        arguments = parser.parse_args(argv)
        rest = list(arguments.rest)
        model = arguments.model
        if model is None and arguments.provider is None:
            model = rest.pop(0)
        provider = arguments.provider or LlmProvider.CLAUDE
        if model is None:
            parser.error("--model is required with --provider")
        known = CodexModel if provider is LlmProvider.CODEX else ClaudeModel
        if model not in set(known):
            parser.error(f"unknown {provider} model {model}; one of: " + ", ".join(known))
        if arguments.effort is not None and provider is not LlmProvider.CODEX:
            parser.error("--effort is for --provider codex only")
        effort = arguments.effort or (CodexEffort.MEDIUM if provider is LlmProvider.CODEX else None)
        try:
            post_ids = [int(value) for value in rest]
        except ValueError:
            parser.error(f"post ids must be numbers: {' '.join(rest)}")
        if not post_ids:
            parser.error("give at least one post id")
        return cls(arguments.source_dir, arguments.target_dir, provider, model, effort, post_ids)


class CountingLlm:
    def __init__(self, inner) -> None:
        self._inner, self.calls = inner, 0

    async def complete_json(self, system, prompt, schema, images=()):
        self.calls += 1
        return await self._inner.complete_json(system, prompt, schema, images)


def readers(comparison: Comparison) -> tuple[list[CountingLlm], object | None]:
    """Three counted readers on the chosen provider, and the Codex runtime to close when Codex reads."""
    if comparison.provider is LlmProvider.CODEX:
        from where_to_go.codex_llm import CodexJsonLlm, CodexRuntime
        from where_to_go.codex_login import CodexHome, ToolGuard, codex_cli

        home = CodexHome.default()
        runtime = CodexRuntime(codex_cli(codex_home=home), home, ToolGuard(home))
        effort = comparison.effort or CodexEffort.MEDIUM
        return [CountingLlm(CodexJsonLlm(lambda: comparison.model, lambda: effort, runtime)) for _ in range(3)], runtime
    from where_to_go.claude_login import claude_cli
    from where_to_go.llm import ClaudeJsonLlm

    claude = claude_cli()
    return [CountingLlm(ClaudeJsonLlm(lambda: comparison.model, claude)) for _ in range(3)], None


def copy_reading_context(origin, target, city_type):
    """The source's city, tags and reading wishes, so both folders read the posts with the same context."""
    old = origin.cities.active()
    city = target.cities.add(city_type(**old.model_dump(exclude={"id"})))
    tags = origin.tags.all()
    target.tags.seed([], next(t.name for t in tags if t.is_fallback))
    for tag in tags:
        if not tag.is_fallback:
            target.tags.add(tag.name, tag.description)
    wishes = origin.settings.load()
    target.settings.update(
        extraction_prompt=wishes.extraction_prompt,
        priority_wish=wishes.priority_wish,
        matching_prompt=wishes.matching_prompt,
        photo_prompt=wishes.photo_prompt,
    )
    return city


async def main(comparison: Comparison) -> None:
    from where_to_go.container import Container
    from where_to_go.models import City, CollectedPost, Source

    origin = Container.build(comparison.source_dir)
    (photos, extraction, matching), runtime = readers(comparison)
    c = Container.build(comparison.target_dir, extraction_llm=extraction, matching_llm=matching, photo_llm=photos)
    try:
        city = c.cities.active() or copy_reading_context(origin, c, City)
        copies: dict[int, Source] = {}
        for post_id in comparison.post_ids:
            post = origin.posts.get(post_id)
            if post.source_id not in copies:
                old = origin.sources.get(post.source_id)
                copies[post.source_id] = c.sources.add(Source(city_id=city.id, handle=old.handle, title=old.title))
            for name in post.image_paths:
                stored = origin.images.path(name)
                if stored is not None:
                    shutil.copy2(stored, comparison.target_dir / "images" / name)
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
        print(
            f"provider={comparison.provider} model={comparison.model} effort={comparison.effort or '-'} "
            f"photo_calls={photos.calls} extraction_calls={extraction.calls} matching_calls={matching.calls} cards={len(touched)}"
        )
    finally:
        if runtime is not None:
            await runtime.close()
        await c.close()
        await origin.close()


if __name__ == "__main__":
    asyncio.run(main(Comparison.parse(sys.argv[1:])))
