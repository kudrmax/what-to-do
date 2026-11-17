from __future__ import annotations

from collections import defaultdict

from where_to_go.images import ImageStore
from where_to_go.models import CollectedPost, Post, Source, SourceKind, TelegramPostLink
from where_to_go.repositories import PostRepository
from where_to_go.telegram import SourceError, TelegramChannelReader


class LinkedPosts:
    """Telegram posts that posts of sources link to, such as the post behind each line of a weekly digest.
    They are kept and read like the source's own posts, so a card gets what the digest line only names.

    One step deep: a linked post's own links are not followed. A post of a channel that is a source belongs to that
    source; any other channel's post belongs to the source whose post links to it."""

    def __init__(self, posts: PostRepository, reader: TelegramChannelReader, images: ImageStore) -> None:
        self._posts = posts
        self._reader = reader
        self._images = images

    async def collect(self, linking: list[Post], city_sources: list[Source]) -> int:
        """Fetches the posts these posts link to and keeps the new ones; a channel that cannot be read is skipped."""
        channels = {s.handle.lower(): s for s in city_sources if s.kind == SourceKind.TELEGRAM}
        wanted = self._links(linking)
        stored = self._posts.stored(link for link, _ in wanted.values())
        numbers: dict[str, set[int]] = defaultdict(set)
        for key, (link, _) in wanted.items():
            if key not in stored:
                numbers[link.handle.lower()].add(link.number)
        added = 0
        for handle, missing in numbers.items():
            try:
                fetched = await self._reader.posts(handle, missing)
            except SourceError:
                continue
            for post in fetched:
                added += await self._keep(post, channels.get(handle), wanted[TelegramPostLink(handle, post.external_id).key][1])
        return added

    async def _keep(self, post: CollectedPost, owner: Source | None, linking: Post) -> bool:
        paths = [p for p in [await self._images.save(u) for u in post.image_urls] if p]
        if owner is not None:
            return self._posts.add_new(owner.id, post, paths, linked=True)
        return self._posts.add_foreign(linking.source_id, post, paths)

    @staticmethod
    def _links(linking: list[Post]) -> dict[str, tuple[TelegramPostLink, Post]]:
        """Each linked post once, with the first post that links to it; only a source's own Telegram posts lead on."""
        wanted: dict[str, tuple[TelegramPostLink, Post]] = {}
        for post in linking:
            if post.linked or post.source.kind != SourceKind.TELEGRAM:
                continue
            for link in TelegramPostLink.all_in(post.text):
                if link.key != post.url.lower():
                    wanted.setdefault(link.key, (link, post))
        return wanted
