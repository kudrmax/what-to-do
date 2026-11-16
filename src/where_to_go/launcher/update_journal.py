from __future__ import annotations

import os
import time
from enum import StrEnum
from pathlib import Path

REPLACE_ATTEMPTS = 50
REPLACE_PAUSE_S = 0.02


def replace_whole(path: Path, text: str) -> None:
    """Writes the file so that a reader sees the old text or the new one, never half. Windows refuses to
    replace a file another process has open for a moment, so it is tried again."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    for attempt in range(REPLACE_ATTEMPTS):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(REPLACE_PAUSE_S)


class UpdateWord(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    DONE = "done"


class StepWord(StrEnum):
    DONE = "done"
    CURRENT = "current"
    PENDING = "pending"
    FAILED = "failed"


class UpdateJournal:
    """What an update writes about itself in the copy's folder, for the app to show while it runs and after
    the restart. Every file is replaced whole: the app reads them at any moment."""

    STATE = ".pids/update.state"
    PID = ".pids/update.pid"
    ERROR = ".pids/update.error"
    # One stage per line: its status, a tab, its title.
    PROGRESS = ".pids/update.progress"
    LOG = ".logs/update.log"
    # Every run's log starts with one of these; the first is that of releases before 1.16.
    RUN_HEADERS = ("=== make update", "=== update")
    PROGRESS_SEPARATOR = "\t"

    def __init__(self, root: Path) -> None:
        self._root = root

    def write_state(self, word: UpdateWord) -> None:
        self.write(self.STATE, word.value)

    def write_pid(self, pid: int) -> None:
        self.write(self.PID, str(pid))

    def write_error(self, text: str) -> None:
        self.write(self.ERROR, text)

    def write_steps(self, steps: list[tuple[StepWord, str]]) -> None:
        self.write(self.PROGRESS, "".join(f"{status.value}{self.PROGRESS_SEPARATOR}{title}\n" for status, title in steps))

    def read(self, relative_path: str) -> str:
        try:
            return (self._root / relative_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def write(self, relative_path: str, text: str) -> None:
        replace_whole(self._root / relative_path, text)
