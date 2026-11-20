"""Which photos show an event: every picture of its posts, a video once, a digest only for this event's line."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FRAME = re.compile(r"^(?P<video>.+)-f\d+\.jpg$")


@dataclass(frozen=True)
class PostPictures:
    image_paths: list[str]
    image_index: int | None
    shared: bool
    """The post is behind several events, so most of its pictures are about the others."""

    def of_event(self) -> list[str]:
        if not self.shared:
            return list(self.image_paths)
        if self.image_index is None or self.image_index >= len(self.image_paths):
            return []
        return [self.image_paths[self.image_index]]


class CardPhotos:
    @staticmethod
    def pick(main: str | None, posts: list[PostPictures]) -> list[str]:
        """The card's main photo first, then the rest in the order of the posts; frames of one video count once."""
        candidates = ([main] if main else []) + [path for post in posts for path in post.of_event()]
        picked: list[str] = []
        videos: set[str] = set()
        for path in candidates:
            frame = _FRAME.match(path)
            if path in picked or (frame and frame["video"] in videos):
                continue
            if frame:
                videos.add(frame["video"])
            picked.append(path)
        return picked
