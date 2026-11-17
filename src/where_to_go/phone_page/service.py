from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from pydantic import Field

from where_to_go.models import Public
from where_to_go.phone_page.cipher import SnapshotCipher
from where_to_go.phone_page.config import PhonePageConfig, PhonePageConfigRepository
from where_to_go.phone_page.github import MARKER, PublishError
from where_to_go.phone_page.snapshot import PhoneSnapshot

log = logging.getLogger(__name__)

BUNDLE_MISSING = "The phone page is not built: run make build"
NO_CITY = "There is no active city to publish plans of"
TURNED_OFF = "The phone page is off"
MISSING_TOKEN = "Enter the token"
MISSING_PASSWORD = "Enter the password"
UNEXPECTED = "Publishing failed unexpectedly. The app log has the details."

PAGE_ENTRY = "phone.html"
INDEX = "index.html"
DATA = "data.bin"
NO_JEKYLL = ".nojekyll"
MARKER_CONTENT = b"Published by What To Do\n"
OFF_PAGE = (
    b'<!doctype html>\n<html lang="en">\n<head><meta charset="utf-8">'
    b'<meta name="viewport" content="width=device-width, initial-scale=1"><title>What To Do</title></head>\n'
    b"<body><p>This page is turned off.</p></body>\n</html>\n"
)


class SnapshotSource(Protocol):
    def build(self, now: datetime) -> tuple[PhoneSnapshot, dict[str, Path]] | None: ...


class PagesPublisher(Protocol):
    async def check(self, repository: str, token: str) -> None: ...

    async def ensure_empty_or_ours(self, repository: str, token: str) -> None: ...

    async def ensure_pages(self, repository: str, token: str) -> str: ...

    async def current_blobs(self, repository: str, token: str) -> dict[str, str]: ...

    async def replace(self, repository: str, token: str, files: dict[str, bytes], reuse: dict[str, str]) -> None: ...


class Cipher(Protocol):
    def encrypt(self, data: bytes) -> bytes: ...

    def encrypt_stable(self, data: bytes) -> bytes: ...


class PhonePageState(Public):
    enabled: bool
    repository: str
    has_token: bool
    has_password: bool
    page_url: str | None = Field(description="The published page; empty until the first turn on")
    published_at: datetime | None = Field(description="When the plans were last published")
    last_error: str | None = Field(description="Why the last publish failed, ready to show")
    publishing: bool = Field(description="A publish is running right now")


class PhonePageService:
    """Publishes the upcoming plans, encrypted, to GitHub Pages: on demand and, while on, when they change."""

    CAP = timedelta(minutes=10)

    def __init__(
        self,
        config: PhonePageConfigRepository,
        builder: SnapshotSource,
        publisher: PagesPublisher,
        cipher_factory: Callable[[str, bytes], Cipher],
        bundle_dir: Path,
        clock: Callable[[], datetime],
        interval: float = 60,
    ) -> None:
        self._config = config
        self._builder = builder
        self._publisher = publisher
        self._cipher_factory = cipher_factory
        self._bundle_dir = bundle_dir
        self._clock = clock
        self._interval = interval
        self._lock = asyncio.Lock()
        self._ciphers: dict[tuple[str, str], Cipher] = {}
        self._task: asyncio.Task | None = None
        self._failed_at: datetime | None = None

    def state(self) -> PhonePageState:
        config = self._config.load()
        return PhonePageState(
            enabled=config.enabled,
            repository=config.repository,
            has_token=bool(config.token),
            has_password=bool(config.password),
            page_url=config.page_url or None,
            published_at=config.published_at,
            last_error=config.last_error,
            publishing=self._lock.locked(),
        )

    async def turn_on(self, repository: str, token: str | None, password: str | None) -> PhonePageState:
        async with self._lock:
            candidate = self._candidate(repository, token, password)
            await self._publisher.check(candidate.repository, candidate.token)
            await self._publisher.ensure_empty_or_ours(candidate.repository, candidate.token)
            published = await self._publish(candidate)
            page_url = await self._publisher.ensure_pages(candidate.repository, candidate.token)
            self._config.update(
                enabled=True,
                repository=candidate.repository,
                token=candidate.token,
                password=candidate.password,
                salt=candidate.salt,
                page_url=page_url,
                **published,
            )
        return self.state()

    def _candidate(self, repository: str, token: str | None, password: str | None) -> PhonePageConfig:
        """The stored config with the new values; `None` keeps the stored secret, a new password gets a new salt."""
        stored = self._config.load()
        candidate = stored.model_copy(update={"repository": repository.strip(), "token": token or stored.token})
        if password and password != stored.password:
            candidate.password = password
            candidate.salt = ""
        if not candidate.salt:
            candidate.salt = base64.b64encode(SnapshotCipher.new_salt()).decode("ascii")
        if not candidate.token:
            raise PublishError(MISSING_TOKEN)
        if not candidate.password:
            raise PublishError(MISSING_PASSWORD)
        return candidate

    async def turn_off(self) -> PhonePageState:
        async with self._lock:
            config = self._config.update(enabled=False, published_hash="")
            if config.repository and config.token:
                try:
                    await self._publisher.replace(config.repository, config.token, {INDEX: OFF_PAGE, MARKER: MARKER_CONTENT}, {})
                except PublishError as error:
                    self._config.update(last_error=str(error))
                    raise
                self._config.update(last_error=None)
        return self.state()

    async def publish_now(self) -> PhonePageState:
        async with self._lock:
            config = self._config.load()
            if not config.enabled:
                raise PublishError(TURNED_OFF)
            await self._publish_safely(config)
        return self.state()

    async def tick(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            config = self._config.load()
            if not config.enabled or self._too_soon(config):
                return
            await self._publish_safely(config, forced=False)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("The phone page tick failed")
            await asyncio.sleep(self._interval)

    def _too_soon(self, config: PhonePageConfig) -> bool:
        attempts = [moment for moment in (config.published_at, self._failed_at) if moment is not None]
        return bool(attempts) and self._clock() - max(attempts) < self.CAP

    async def _publish_safely(self, config: PhonePageConfig, forced: bool = True) -> None:
        attempted_at = self._clock()
        try:
            published = await self._publish(config, forced)
        except PublishError as error:
            self._failed_at = attempted_at
            self._config.update(last_error=str(error))
        except Exception:
            self._failed_at = attempted_at
            log.exception("Publishing the phone page failed")
            self._config.update(last_error=UNEXPECTED)
        else:
            if published:
                self._failed_at = None
                self._config.update(**published)

    async def _publish(self, config: PhonePageConfig, forced: bool = True) -> dict[str, object]:
        """Uploads the plans when forced or when they or the page changed; returns the config change to store, empty when skipped."""
        now = self._clock()
        built = await asyncio.to_thread(self._builder.build, now)
        if built is None:
            raise PublishError(NO_CITY)
        snapshot, posters = built
        bundle = await asyncio.to_thread(self._bundle)
        version = snapshot.content_hash() + _digest(bundle) + config.salt
        if not forced and version == config.published_hash:
            return {}
        known = await self._publisher.current_blobs(config.repository, config.token) if self._same_key(config) else {}
        files, reuse = await asyncio.to_thread(self._content, config, bundle, snapshot, posters, known)
        await self._publisher.replace(config.repository, config.token, files, reuse)
        return {
            "published_hash": version,
            "published_at": now,
            "last_error": None if bundle else BUNDLE_MISSING,
        }

    @staticmethod
    def _same_key(config: PhonePageConfig) -> bool:
        """Posters already on GitHub were encrypted with the key of the last publish; a new salt means a new key."""
        return bool(config.published_hash) and config.published_hash.endswith(config.salt)

    def _content(
        self, config: PhonePageConfig, bundle: dict[str, bytes], snapshot: PhoneSnapshot, posters: dict[str, Path], known: dict[str, str]
    ) -> tuple[dict[str, bytes], dict[str, str]]:
        """The files to upload, and the posters already on GitHub to keep by their blob."""
        cipher = self._cipher(config)
        files = {**bundle, DATA: cipher.encrypt(snapshot.model_dump_json().encode("utf-8"))}
        reuse = {}
        for path, source in posters.items():
            if path in known:
                reuse[path] = known[path]
            else:
                files[path] = cipher.encrypt_stable(source.read_bytes())
        files[NO_JEKYLL] = b""
        files[MARKER] = MARKER_CONTENT
        return files, reuse

    def _bundle(self) -> dict[str, bytes]:
        if not self._bundle_dir.is_dir():
            return {}
        files = {}
        for path in sorted(self._bundle_dir.rglob("*")):
            if path.is_file():
                name = path.relative_to(self._bundle_dir).as_posix()
                files[INDEX if name == PAGE_ENTRY else name] = path.read_bytes()
        return files

    def _cipher(self, config: PhonePageConfig) -> Cipher:
        key = (config.password, config.salt)
        if key not in self._ciphers:
            self._ciphers = {key: self._cipher_factory(config.password, base64.b64decode(config.salt))}
        return self._ciphers[key]


def _digest(files: dict[str, bytes]) -> str:
    """Tells one build of the page bundle from another, so a new app release republishes the page."""
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(files[name]).digest())
    return digest.hexdigest()[:16]
