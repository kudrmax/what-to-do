from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass
class _Followed:
    label: str
    path: Path
    offset: int = 0
    pending: str = ""


class LogFollower:
    """The logs of the app and of its updates in one stream, each line marked with where it came from."""

    POLL_S = 0.5

    def __init__(self, sources: list[tuple[str, Path]], say: Callable[[str], None] = print) -> None:
        width = max(len(label) for label, _ in sources)
        self._files = [_Followed(label.ljust(width), path) for label, path in sources]
        self._say = say

    def run(self, lines: int, follow: bool) -> None:
        for followed in self._files:
            for line in self._tail(followed, lines):
                self._say(f"{followed.label} | {line}")
        while follow:
            time.sleep(self.POLL_S)
            for followed in self._files:
                for line in self._new_lines(followed):
                    self._say(f"{followed.label} | {line}")

    @staticmethod
    def _tail(followed: _Followed, lines: int) -> list[str]:
        try:
            data = followed.path.read_bytes()
        except OSError:
            return []
        followed.offset = len(data)
        return data.decode("utf-8", errors="replace").splitlines()[-lines:] if lines > 0 else []

    @staticmethod
    def _new_lines(followed: _Followed) -> list[str]:
        try:
            size = followed.path.stat().st_size
        except OSError:
            return []
        if size < followed.offset:
            followed.offset, followed.pending = 0, ""
        if size == followed.offset:
            return []
        with followed.path.open("rb") as file:
            file.seek(followed.offset)
            chunk = file.read()
        followed.offset += len(chunk)
        text = followed.pending + chunk.decode("utf-8", errors="replace")
        *complete, followed.pending = text.split("\n")
        return [line.rstrip("\r") for line in complete]
