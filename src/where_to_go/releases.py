from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Callable, Protocol

from pydantic import BaseModel

from where_to_go.updating import UpdateRunner

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parents[2]
CHANGELOG_FILE = "CHANGELOG.md"
CHANGELOG_IMAGES_DIR = PurePosixPath("docs/images/changelog")


@dataclass(frozen=True, order=True)
class AppVersion:
    """A release number `major.minor.patch`; versions compare numerically."""

    major: int
    minor: int
    patch: int

    PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")

    @classmethod
    def parse(cls, text: str) -> AppVersion:
        match = cls.PATTERN.fullmatch(text.strip())
        if match is None:
            raise ValueError(f"Not a version: {text!r}")
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    @classmethod
    def parse_or_none(cls, text: str | None) -> AppVersion | None:
        try:
            return cls.parse(text) if text else None
        except ValueError:
            return None

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class ChangelogSection(BaseModel):
    """One `###` block of a release: a big feature or a group such as "Новое"."""

    title: str
    body_markdown: str


class ChangelogEntry(BaseModel):
    """One released version: its one-line summary and sections, in file order."""

    version: str
    released_on: date
    summary: str
    sections: list[ChangelogSection]

    @property
    def app_version(self) -> AppVersion:
        return AppVersion.parse(self.version)


class Changelog:
    """CHANGELOG.md read into entries, newest first as the file lists them."""

    ENTRY_PREFIX = "## "
    SECTION_PREFIX = "### "
    ENTRY_HEADING = re.compile(r"## (\S+) — (\d{4}-\d{2}-\d{2})")

    @classmethod
    def parse(cls, text: str) -> list[ChangelogEntry]:
        entries: list[ChangelogEntry] = []
        heading: str | None = None
        block: list[str] = []
        for line in text.splitlines():
            if line.startswith(cls.ENTRY_PREFIX):
                if heading is not None:
                    entries.append(cls._entry(heading, block))
                heading, block = line, []
            elif heading is not None:
                block.append(line)
        if heading is not None:
            entries.append(cls._entry(heading, block))
        return entries

    @classmethod
    def between(cls, text: str, after: AppVersion, upto: AppVersion) -> list[ChangelogEntry]:
        return [entry for entry in cls.parse(text) if after < entry.app_version <= upto]

    @classmethod
    def _entry(cls, heading: str, lines: list[str]) -> ChangelogEntry:
        match = cls.ENTRY_HEADING.fullmatch(heading.rstrip())
        if match is None:
            raise ValueError(f"Malformed changelog heading: {heading!r}")
        try:
            version = AppVersion.parse(match.group(1))
            released_on = date.fromisoformat(match.group(2))
        except ValueError as error:
            raise ValueError(f"Malformed changelog heading: {heading!r} ({error})") from error
        summary: list[str] = []
        sections: list[tuple[str, list[str]]] = []
        for line in lines:
            if line.startswith(cls.SECTION_PREFIX):
                sections.append((line[len(cls.SECTION_PREFIX):].strip(), []))
            elif sections:
                sections[-1][1].append(line)
            else:
                summary.append(line)
        return ChangelogEntry(
            version=str(version),
            released_on=released_on,
            summary="\n".join(summary).strip(),
            sections=[ChangelogSection(title=title, body_markdown="\n".join(body).strip()) for title, body in sections],
        )


def is_changelog_asset(path: str) -> bool:
    """Only files under the changelog images folder may leave a release."""
    candidate = PurePosixPath(path)
    return (
        not candidate.is_absolute()
        and ".." not in candidate.parts
        and candidate.is_relative_to(CHANGELOG_IMAGES_DIR)
        and candidate != CHANGELOG_IMAGES_DIR
    )


class InstalledRelease:
    """The release checked out in the project folder. Its version is the one the server started with:
    a checkout under a running server does not change the code it runs."""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        with (project_dir / "pyproject.toml").open("rb") as pyproject:
            self.version = AppVersion.parse(tomllib.load(pyproject)["project"]["version"])

    def changelog_text(self) -> str:
        path = self._project_dir / CHANGELOG_FILE
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def asset(self, path: str) -> bytes | None:
        if not is_changelog_asset(path):
            return None
        file = self._project_dir / path
        return file.read_bytes() if file.is_file() else None


class ReleaseSource(Protocol):
    """Published releases the installed copy may not have yet."""

    def latest(self) -> AppVersion | None:
        """Fetches the newest published version; None when it cannot be learned."""
        ...

    def changelog_text(self, version: AppVersion) -> str | None: ...

    def asset(self, version: AppVersion, path: str) -> bytes | None: ...


class GitReleases:
    """Releases are the `vX.Y.Z` tags of the project folder's git remote."""

    TIMEOUT_S = 20
    # Runs unattended: a git asking for a password would hang the request.
    NON_INTERACTIVE = {"GIT_TERMINAL_PROMPT": "0"}

    def __init__(self, project_dir: Path, git: Callable[..., bytes] | None = None) -> None:
        self._project_dir = project_dir
        self._git = git or self._run_git

    def latest(self) -> AppVersion | None:
        try:
            self._git("fetch", "--tags", "--force", "--quiet", "origin")
            tags = self._git("tag", "--list", "v*").decode().split()
        except (OSError, RuntimeError) as error:
            logger.warning("Could not learn the latest release: %s", error)
            return None
        return max((version for tag in tags if (version := AppVersion.parse_or_none(tag))), default=None)

    def changelog_text(self, version: AppVersion) -> str | None:
        content = self._show(version, CHANGELOG_FILE)
        return content.decode("utf-8", errors="replace") if content is not None else None

    def asset(self, version: AppVersion, path: str) -> bytes | None:
        return self._show(version, path) if is_changelog_asset(path) else None

    def _show(self, version: AppVersion, path: str) -> bytes | None:
        try:
            return self._git("show", f"v{version}:{path}")
        except (OSError, RuntimeError) as error:
            logger.warning("Could not read %s of release %s: %s", path, version, error)
            return None

    def _run_git(self, *args: str) -> bytes:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self._project_dir,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                env={**os.environ, **self.NON_INTERACTIVE},
                timeout=self.TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"git {args[0]} timed out") from error
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.decode(errors="replace").strip())
        return completed.stdout


class ReleaseMemory:
    """What the app remembers about releases between runs, in a small JSON file of the data folder."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def get(self, key: str) -> str | None:
        value = self._read().get(key)
        return value if isinstance(value, str) else None

    def set(self, **values: str) -> None:
        data = self._read() | values
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)

    def time(self, key: str) -> datetime | None:
        try:
            stored = self.get(key)
            return datetime.fromisoformat(stored) if stored else None
        except ValueError:
            return None

    def _read(self) -> dict[str, object]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}


class UpdateStatus(BaseModel):
    """What the copy knows about newer releases. `entries` are the changes an update brings; `check_failed`
    is set when an explicit check could not reach the releases. The commands are what a person types in
    a terminal when the update from the app hangs or fails."""

    current: str
    latest: str | None
    available: bool
    entries: list[ChangelogEntry]
    check_failed: bool
    restart_command: str
    update_command: str


class UpdateCheck:
    """Tells whether a newer release exists. The releases are asked at most once a day, a failed ask is
    tried again within the hour; `force` asks again."""

    INTERVAL = timedelta(days=1)
    # Offline, every page load would wait on a fetch that fails; this spaces the attempts out.
    RETRY_INTERVAL = timedelta(hours=1)
    CHECKED_AT = "update_checked_at"
    RETRY_AT = "update_retry_at"
    LATEST = "update_latest_version"

    def __init__(
        self,
        installed: InstalledRelease,
        source: ReleaseSource,
        memory: ReleaseMemory,
        commands: UpdateCommands,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._installed = installed
        self._source = source
        self._memory = memory
        self._commands = commands
        self._now = now

    def status(self, force: bool) -> UpdateStatus:
        current = self._installed.version
        fetch_failed = False
        if not force and (self._fresh() or self._retry_pending()):
            latest = self._remembered_latest()
        else:
            fetched = self._source.latest()
            fetch_failed = fetched is None
            self._remember(fetched)
            latest = fetched or self._remembered_latest()
        available = latest is not None and latest > current
        entries: list[ChangelogEntry] = []
        if available and latest is not None:
            text = self._source.changelog_text(latest)
            entries = Changelog.between(text, current, latest) if text else []
        return UpdateStatus(
            current=str(current),
            latest=str(latest) if latest else None,
            available=available,
            entries=entries,
            check_failed=force and fetch_failed,
            restart_command=self._commands.restart(),
            update_command=self._commands.update(),
        )

    def _fresh(self) -> bool:
        checked_at = self._memory.time(self.CHECKED_AT)
        return checked_at is not None and self._now() - checked_at < self.INTERVAL

    def _retry_pending(self) -> bool:
        retry_at = self._memory.time(self.RETRY_AT)
        return retry_at is not None and self._now() < retry_at

    def _remembered_latest(self) -> AppVersion | None:
        return AppVersion.parse_or_none(self._memory.get(self.LATEST))

    def _remember(self, fetched: AppVersion | None) -> None:
        now = self._now()
        if fetched is None:
            self._memory.set(**{self.RETRY_AT: (now + self.RETRY_INTERVAL).isoformat()})
        else:
            self._memory.set(**{self.CHECKED_AT: now.isoformat(), self.LATEST: str(fetched)})


class WhatsNew:
    """The changelog of the installed copy and what in it the user has not seen yet."""

    SEEN = "changelog_seen_version"

    def __init__(self, installed: InstalledRelease, memory: ReleaseMemory) -> None:
        self._installed = installed
        self._memory = memory

    def all(self) -> list[ChangelogEntry]:
        return Changelog.parse(self._installed.changelog_text())

    def unseen(self) -> list[ChangelogEntry]:
        seen = AppVersion.parse_or_none(self._memory.get(self.SEEN))
        if seen is None:
            # A fresh install has nothing new to tell.
            self.mark_seen()
            return []
        return Changelog.between(self._installed.changelog_text(), seen, self._installed.version)

    def mark_seen(self) -> None:
        self._memory.set(**{self.SEEN: str(self._installed.version)})


class UpdateCommands:
    """What a person types in a terminal to restart or update this copy by hand."""

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir

    def restart(self) -> str:
        return f"cd {shlex.quote(str(self._project_dir))} && make down && make up"

    def update(self) -> str:
        return f"cd {shlex.quote(str(self._project_dir))} && make update"


@dataclass
class Releases:
    """Everything about the copy's version: what is installed, what is published, updating to it."""

    installed: InstalledRelease
    source: ReleaseSource
    check: UpdateCheck
    whats_new: WhatsNew
    runner: UpdateRunner

    @classmethod
    def build(cls, project_dir: Path, data_dir: Path, source: ReleaseSource | None = None) -> Releases:
        installed = InstalledRelease(project_dir)
        source = source or GitReleases(project_dir)
        memory = ReleaseMemory(data_dir / "releases.json")
        return cls(
            installed=installed,
            source=source,
            check=UpdateCheck(installed, source, memory, UpdateCommands(project_dir)),
            whats_new=WhatsNew(installed, memory),
            runner=UpdateRunner(project_dir),
        )

    def asset(self, version: AppVersion, path: str) -> bytes | None:
        if version == self.installed.version:
            return self.installed.asset(path)
        return self.source.asset(version, path)
