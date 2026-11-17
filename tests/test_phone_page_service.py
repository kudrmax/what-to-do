import asyncio
import base64
import hashlib
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from where_to_go.db import Database
from where_to_go.phone_page.config import PhonePageConfigRepository
from where_to_go.phone_page.github import MARKER, PublishError
from where_to_go.phone_page.service import BUNDLE_MISSING, PhonePageService
from where_to_go.phone_page.snapshot import PhoneOccurrence, PhoneSnapshot

START = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
REPOSITORY = "max/plans"
TOKEN = "ghp_secret_token"
PASSWORD = "phone password"


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, minutes: int) -> None:
        self.now += timedelta(minutes=minutes)


class FakeBuilder:
    def __init__(self) -> None:
        self.titles = ["Concert"]
        self.posters: dict[str, Path] = {}

    def build(self, now: datetime) -> tuple[PhoneSnapshot, dict[str, Path]]:
        occurrences = [PhoneOccurrence(date=date(2026, 11, 18), event={"title": t}, post_url=None) for t in self.titles]
        snapshot = PhoneSnapshot(made_at=now, city="Belgrade", timezone="Europe/Belgrade", today=now.date(), tags=[], occurrences=occurrences)
        return snapshot, dict(self.posters)


class FakeCipher:
    def __init__(self, password: str, salt: bytes) -> None:
        self.prefix = b"enc[" + salt + password.encode() + b"]"

    def encrypt(self, data: bytes) -> bytes:
        return self.prefix + data

    def encrypt_stable(self, data: bytes) -> bytes:
        return self.prefix + b"stable:" + data


class FakePublisher:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.published: list[dict[str, bytes]] = []
        self.reused: list[dict[str, str]] = []
        self.tree: dict[str, str] = {}
        self.failing: dict[str, str] = {}

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.failing:
            raise PublishError(self.failing[name])

    async def check(self, repository: str, token: str) -> None:
        self._call("check")

    async def ensure_empty_or_ours(self, repository: str, token: str) -> None:
        self._call("ensure_empty_or_ours")

    async def ensure_pages(self, repository: str, token: str) -> str:
        self._call("ensure_pages")
        return "https://max.github.io/plans/"

    async def current_blobs(self, repository: str, token: str) -> dict[str, str]:
        self._call("current_blobs")
        return dict(self.tree)

    async def replace(self, repository: str, token: str, files: dict[str, bytes], reuse: dict[str, str]) -> None:
        self._call("replace")
        self.published.append(files)
        self.reused.append(reuse)
        self.tree = {**reuse, **{path: hashlib.sha1(content).hexdigest() for path, content in files.items()}}

    @property
    def publishes(self) -> int:
        return self.calls.count("replace")


@pytest.fixture
def bundle(tmp_path):
    folder = tmp_path / "phone"
    (folder / "assets").mkdir(parents=True)
    (folder / "phone.html").write_text("<html>phone</html>")
    (folder / "assets" / "phone.js").write_text("console.log(1)")
    return folder


@pytest.fixture
def config():
    return PhonePageConfigRepository(Database(":memory:"))


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def builder():
    return FakeBuilder()


@pytest.fixture
def publisher():
    return FakePublisher()


@pytest.fixture
def service(config, builder, publisher, bundle, clock):
    return PhonePageService(config, builder, publisher, FakeCipher, bundle, clock)


async def test_turn_on_runs_the_steps_in_order_and_publishes(service, publisher):
    state = await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    assert [c for c in publisher.calls if c != "current_blobs"] == ["check", "ensure_empty_or_ours", "replace", "ensure_pages"]
    assert state.enabled and state.has_token and state.has_password
    assert state.page_url == "https://max.github.io/plans/"
    assert state.published_at == START and state.last_error is None
    files = publisher.published[0]
    assert set(files) == {"index.html", "assets/phone.js", "data.bin", ".nojekyll", MARKER}
    assert files["index.html"] == b"<html>phone</html>"
    assert files["data.bin"].startswith(b"enc[") and b'"title":"Concert"' in files["data.bin"]
    assert not any(b"Concert" in content for path, content in files.items() if path != "data.bin")


async def test_state_never_shows_secrets(service):
    state = await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    dumped = state.model_dump_json()
    assert TOKEN not in dumped and PASSWORD not in dumped


async def test_tick_does_nothing_while_off(service, publisher):
    await service.tick()

    assert publisher.calls == []


async def test_tick_publishes_on_change_only(service, publisher, builder, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    clock.advance(30)

    await service.tick()
    assert publisher.publishes == 1

    builder.titles.append("Lecture")
    await service.tick()
    assert publisher.publishes == 2
    assert service.state().published_at == clock.now


async def test_tick_waits_ten_minutes_between_publishes(service, publisher, builder, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    builder.titles.append("Lecture")

    clock.advance(3)
    await service.tick()
    assert publisher.publishes == 1

    clock.advance(7)
    await service.tick()
    assert publisher.publishes == 2


async def test_publish_now_ignores_the_cap(service, publisher, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    clock.advance(1)

    state = await service.publish_now()

    assert publisher.publishes == 2
    assert state.published_at == clock.now


async def test_publish_now_refused_while_off(service, publisher):
    with pytest.raises(PublishError):
        await service.publish_now()

    assert publisher.calls == []


async def test_known_posters_are_reused_not_uploaded(service, publisher, builder, clock, tmp_path):
    poster = tmp_path / "abc.jpg"
    poster.write_bytes(b"jpeg")
    builder.posters = {"images/abc.bin": poster}
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    assert publisher.published[0]["images/abc.bin"].endswith(b"stable:jpeg")
    poster_sha = publisher.tree["images/abc.bin"]

    builder.titles.append("Lecture")
    clock.advance(10)
    await service.tick()

    assert "images/abc.bin" not in publisher.published[1]
    assert publisher.reused[1] == {"images/abc.bin": poster_sha}


async def test_posters_are_uploaded_again_after_a_new_password(service, publisher, builder, tmp_path):
    poster = tmp_path / "abc.jpg"
    poster.write_bytes(b"jpeg")
    builder.posters = {"images/abc.bin": poster}
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    await service.turn_on(REPOSITORY, None, "another password")

    assert "images/abc.bin" in publisher.published[1]
    assert publisher.reused[1] == {}


async def test_turn_on_refused_stays_off(service, publisher, config):
    publisher.failing["ensure_empty_or_ours"] = "This repository already has other files. Create a new empty one."

    with pytest.raises(PublishError, match="other files"):
        await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    assert not service.state().enabled
    assert publisher.publishes == 0
    await service.tick()
    assert publisher.publishes == 0


async def test_turn_on_needs_a_token_and_a_password(service, publisher):
    with pytest.raises(PublishError):
        await service.turn_on(REPOSITORY, None, PASSWORD)
    with pytest.raises(PublishError):
        await service.turn_on(REPOSITORY, TOKEN, None)

    assert publisher.calls == []


async def test_turn_on_keeps_stored_secrets_when_none(service, config):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    salt = config.load().salt

    await service.turn_on(REPOSITORY, None, None)

    stored = config.load()
    assert stored.token == TOKEN and stored.password == PASSWORD and stored.salt == salt


async def test_new_password_makes_new_salt(service, config, publisher):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    first = config.load().salt
    assert len(base64.b64decode(first)) == 16

    await service.turn_on(REPOSITORY, None, PASSWORD)
    assert config.load().salt == first

    await service.turn_on(REPOSITORY, None, "another password")
    assert config.load().salt != first
    assert publisher.published[-1]["data.bin"].startswith(b"enc[" + base64.b64decode(config.load().salt))


async def test_new_password_forces_a_publish_on_tick(service, publisher, config, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    config.update(password="another password", salt=base64.b64encode(b"x" * 16).decode())
    clock.advance(10)

    await service.tick()

    assert publisher.publishes == 2


async def test_turn_off_leaves_no_data(service, publisher, config):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    state = await service.turn_off()

    assert set(publisher.published[-1]) == {"index.html", MARKER}
    assert publisher.reused[-1] == {}
    assert b"turned off" in publisher.published[-1]["index.html"]
    assert not state.enabled and state.has_token and state.has_password
    assert config.load().token == TOKEN


async def test_tick_does_nothing_after_turn_off(service, publisher, builder, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    await service.turn_off()
    builder.titles.append("Lecture")
    clock.advance(30)

    await service.tick()

    assert publisher.publishes == 2


async def test_failed_publish_is_kept_in_state_and_retried(service, publisher, builder, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    builder.titles.append("Lecture")
    clock.advance(10)
    publisher.failing["replace"] = "Could not reach GitHub. Check the internet connection."

    await service.tick()

    state = service.state()
    assert state.last_error == "Could not reach GitHub. Check the internet connection."
    assert state.published_at == START
    del publisher.failing["replace"]
    clock.advance(10)
    await service.tick()
    assert publisher.publishes == 3
    assert service.state().last_error is None


async def test_failed_publish_waits_ten_minutes_before_the_next_attempt(service, publisher, builder, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    builder.titles.append("Lecture")
    clock.advance(30)
    publisher.failing["replace"] = "The token expired or was revoked"
    await service.tick()
    attempts = publisher.calls.count("replace")

    clock.advance(9)
    await service.tick()
    assert publisher.calls.count("replace") == attempts

    clock.advance(1)
    await service.tick()
    assert publisher.calls.count("replace") == attempts + 1


async def test_publish_now_ignores_the_wait_after_a_failure(service, publisher, builder, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    builder.titles.append("Lecture")
    clock.advance(30)
    publisher.failing["replace"] = "Could not reach GitHub. Check the internet connection."
    await service.tick()
    del publisher.failing["replace"]
    clock.advance(1)

    state = await service.publish_now()

    assert state.last_error is None and state.published_at == clock.now


async def test_turn_on_again_after_pages_were_turned_on_by_hand(service, publisher):
    publisher.failing["ensure_pages"] = "Turn on GitHub Pages for this repository"
    with pytest.raises(PublishError):
        await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    assert publisher.publishes == 1 and not service.state().enabled

    del publisher.failing["ensure_pages"]
    state = await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    assert state.enabled and state.page_url == "https://max.github.io/plans/" and state.last_error is None
    assert publisher.publishes == 2


async def test_turn_on_without_a_bundle_fails_and_publishes_nothing(config, builder, publisher, clock, tmp_path):
    service = PhonePageService(config, builder, publisher, FakeCipher, tmp_path / "absent", clock)

    with pytest.raises(PublishError, match=BUNDLE_MISSING):
        await service.turn_on(REPOSITORY, TOKEN, PASSWORD)

    assert publisher.publishes == 0
    assert not service.state().enabled


async def test_tick_without_a_bundle_publishes_nothing_and_says_so(service, publisher, builder, bundle, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    bundle.rename(bundle.with_name("gone"))
    builder.titles.append("Lecture")
    clock.advance(10)

    await service.tick()

    assert publisher.publishes == 1
    assert service.state().last_error == BUNDLE_MISSING


async def test_loop_ticks_and_stops(config, builder, publisher, bundle, clock):
    service = PhonePageService(config, builder, publisher, FakeCipher, bundle, clock, interval=0.01)
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    builder.titles.append("Lecture")
    clock.advance(10)

    service.start()
    for _ in range(100):
        if publisher.publishes == 2:
            break
        await asyncio.sleep(0.01)
    await service.stop()

    assert publisher.publishes == 2


async def test_new_page_bundle_is_published(service, publisher, bundle, clock):
    await service.turn_on(REPOSITORY, TOKEN, PASSWORD)
    (bundle / "assets" / "phone.js").write_text("console.log(2)")
    clock.advance(10)

    await service.tick()

    assert publisher.publishes == 2
    assert publisher.published[-1]["assets/phone.js"] == b"console.log(2)"


async def test_a_failing_tick_does_not_end_the_loop(config, builder, publisher, bundle, clock, monkeypatch):
    service = PhonePageService(config, builder, publisher, FakeCipher, bundle, clock, interval=0.01)
    ticks = 0

    async def broken_tick() -> None:
        nonlocal ticks
        ticks += 1
        raise RuntimeError("database is locked")

    monkeypatch.setattr(service, "tick", broken_tick)
    service.start()
    for _ in range(100):
        if ticks >= 3:
            break
        await asyncio.sleep(0.01)

    await service.stop()

    assert ticks >= 3
