"""A copy of the data folder never carries the right to publish to the owner's GitHub."""

import os
import shlex
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from tests.helpers import BELGRADE
from where_to_go.api import create_app
from where_to_go.container import Container
from where_to_go.db import Database
from where_to_go.models import Setting
from where_to_go.phone_page.secrets import KeychainSecret, SecretStoreError

TOKEN = "ghp_owner_token"
LEGACY = "ghp_token_from_an_old_database"

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="the keychain exists on macOS only; Windows keeps the token in memory, and its data folder paths "
    "carry backslashes that `security -i` cannot take as the keychain account",
)


class FakeSecurity:
    """The macOS `security` tool over an in-memory keychain, remembering every command line it was given."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}
        self.command_lines: list[list[str]] = []

    def __call__(self, command: list[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
        self.command_lines.append(command)
        if command == ["security", "-i"]:
            command = ["security", *shlex.split(stdin or "")]
        verb, options = command[1], self._options(command[2:])
        key = (options["-s"], options["-a"])
        if verb == "add-generic-password":
            self.items[key] = options["-w"]
            return self._done()
        if key not in self.items:
            return self._done(44, "The specified item could not be found in the keychain.")
        if verb == "delete-generic-password":
            del self.items[key]
            return self._done()
        return self._done(stdout=self.items[key] + "\n")

    @staticmethod
    def _options(words: list[str]) -> dict[str, str]:
        options, name = {}, None
        for word in words:
            if word.startswith("-"):
                name = word
                options[name] = ""
            elif name:
                options[name] = word
                name = None
        return options

    @staticmethod
    def _done(code: int = 0, stderr: str = "", stdout: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], code, stdout, stderr)


class RecordingPublisher:
    """GitHub as the app sees it: every request to it is a touch of the owner's account."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def check(self, repository, token):
        self.calls.append(("check", repository, token))

    async def ensure_empty_or_ours(self, repository, token):
        self.calls.append(("ensure_empty_or_ours", repository, token))

    async def ensure_pages(self, repository, token):
        self.calls.append(("ensure_pages", repository, token))
        return "https://max.github.io/plans/"

    async def current_blobs(self, repository, token):
        self.calls.append(("current_blobs", repository, token))
        return {}

    async def replace(self, repository, token, files, reuse):
        self.calls.append(("replace", repository, token))


@pytest.fixture
def keychain():
    return FakeSecurity()


@pytest.fixture
def owner_dir(tmp_path):
    return tmp_path / "Application Support" / "where-to-go"


def instance(data_dir, owner_dir, keychain, publisher):
    bundle = data_dir.parent / f"{data_dir.name}-bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "phone.html").write_text("<html>phone</html>")
    app = create_app(
        lambda: Container.build(
            data_dir,
            phone_publisher=publisher,
            phone_bundle=bundle,
            phone_token=KeychainSecret(data_dir, run=keychain),
            primary_data_dir=owner_dir,
        )
    )
    return TestClient(app)


def turn_on_in_owner(owner_dir, keychain):
    publisher = RecordingPublisher()
    with instance(owner_dir, owner_dir, keychain, publisher) as client:
        client.post("/cities", json=BELGRADE)
        assert client.put("/phone-page", json={"repository": "max/plans", "token": TOKEN, "password": "pw"}).status_code == 200
    return publisher


def stored_token_rows(data_dir):
    with Database(data_dir / "where-to-go.sqlite3").session() as s:
        return [row.value for row in s.exec(select(Setting).where(Setting.key == "phone_page.token"))]


def write_legacy_token(data_dir):
    with Database(data_dir / "where-to-go.sqlite3").session() as s:
        s.merge(Setting(key="phone_page.token", value=LEGACY))
        s.commit()


def assert_cannot_publish(client, publisher):
    state = client.get("/phone-page").json()
    assert state["enabled"] is False and state["has_token"] is False
    assert client.post("/phone-page/publish").status_code == 409
    client.portal.call(client.app.state.container.phone_page.tick)
    client.delete("/phone-page")
    assert publisher.calls == []


def test_the_token_lives_in_the_keychain_not_in_the_data_folder(owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)

    assert stored_token_rows(owner_dir) == []
    assert TOKEN.encode() not in (owner_dir / "where-to-go.sqlite3").read_bytes()
    assert keychain.items == {(KeychainSecret.SERVICE, str(owner_dir.resolve())): TOKEN}


def test_the_token_never_reaches_a_command_line(owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)

    assert keychain.command_lines and all(TOKEN not in word for line in keychain.command_lines for word in line)


def test_the_owner_keeps_publishing_after_a_restart(owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)
    publisher = RecordingPublisher()
    with instance(owner_dir, owner_dir, keychain, publisher) as client:
        assert client.get("/phone-page").json()["enabled"] is True
        assert client.post("/phone-page/publish").status_code == 200
    assert ("replace", "max/plans", TOKEN) in publisher.calls


def test_a_copy_of_the_data_folder_cannot_publish(tmp_path, owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)
    copy = tmp_path / "worktree" / "data"
    shutil.copytree(owner_dir, copy)

    publisher = RecordingPublisher()
    with instance(copy, owner_dir, keychain, publisher) as client:
        assert_cannot_publish(client, publisher)


def test_a_copy_of_an_old_database_drops_its_token_unused(tmp_path, owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)
    copy = tmp_path / "worktree" / "data"
    shutil.copytree(owner_dir, copy)
    write_legacy_token(copy)

    publisher = RecordingPublisher()
    with instance(copy, owner_dir, keychain, publisher) as client:
        assert_cannot_publish(client, publisher)
    assert stored_token_rows(copy) == []
    assert LEGACY not in keychain.items.values()


def test_the_owner_moves_its_old_token_to_the_keychain_on_update(owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)
    keychain.items.clear()
    write_legacy_token(owner_dir)

    publisher = RecordingPublisher()
    with instance(owner_dir, owner_dir, keychain, publisher) as client:
        state = client.get("/phone-page").json()
        assert state["enabled"] is True and state["has_token"] is True
        assert client.post("/phone-page/publish").status_code == 200
    assert ("replace", "max/plans", LEGACY) in publisher.calls
    assert stored_token_rows(owner_dir) == []
    assert keychain.items == {(KeychainSecret.SERVICE, str(owner_dir.resolve())): LEGACY}


def test_the_owner_keeps_its_old_token_when_the_keychain_refuses(owner_dir, keychain):
    turn_on_in_owner(owner_dir, keychain)
    keychain.items.clear()
    write_legacy_token(owner_dir)

    def refusing(command, stdin):
        if command == ["security", "-i"]:
            return subprocess.CompletedProcess([], 1, "", "User interaction is not allowed.")
        return keychain(command, stdin)

    with instance(owner_dir, owner_dir, refusing, RecordingPublisher()):
        pass
    assert stored_token_rows(owner_dir) == [LEGACY]


def test_turning_on_reports_a_keychain_refusal(owner_dir):
    def refusing(command, stdin):
        if command == ["security", "-i"]:
            return subprocess.CompletedProcess([], 1, "", "User interaction is not allowed.")
        return subprocess.CompletedProcess([], 44, "", "")

    with instance(owner_dir, owner_dir, refusing, RecordingPublisher()) as client:
        client.post("/cities", json=BELGRADE)
        response = client.put("/phone-page", json={"repository": "max/plans", "token": TOKEN, "password": "pw"})
        assert response.status_code == 422
        assert "keychain" in response.json()["detail"] and TOKEN not in response.text


def test_the_keychain_refuses_values_it_cannot_quote(tmp_path, keychain):
    with pytest.raises(SecretStoreError):
        KeychainSecret(tmp_path, run=keychain).write('to"ken')
