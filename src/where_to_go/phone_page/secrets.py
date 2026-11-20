from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)


class SecretStore(Protocol):
    """Keeps one secret of this installation outside its data folder, so a copy of the data never carries it."""

    def read(self) -> str: ...

    def write(self, secret: str) -> None: ...


class SecretStoreError(Exception):
    pass


class MemorySecret:
    """Lives only while the process runs: for tests and for platforms without a keychain."""

    def __init__(self, secret: str = "") -> None:
        self._secret = secret

    def read(self) -> str:
        return self._secret

    def write(self, secret: str) -> None:
        self._secret = secret


Runner = Callable[[list[str], str | None], subprocess.CompletedProcess[str]]


def _run(command: list[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=stdin, capture_output=True, text=True, timeout=30, check=False)


class KeychainSecret:
    """A generic password in the macOS login keychain, owned by the data folder it belongs to.

    The account is the data folder's path, so a copy of the data in another folder finds nothing. The secret
    goes to `security` on its standard input, never on its command line where other processes could see it."""

    SERVICE = "What To Do phone page token"
    NOT_FOUND = 44

    def __init__(self, data_dir: Path, run: Runner = _run) -> None:
        self._account = str(data_dir.expanduser().resolve())
        self._run = run

    def read(self) -> str:
        done = self._run(["security", "find-generic-password", "-s", self.SERVICE, "-a", self._account, "-w"], None)
        if done.returncode == self.NOT_FOUND:
            return ""
        if done.returncode != 0:
            raise SecretStoreError(f"The keychain did not give the token: {done.stderr.strip()}")
        return done.stdout.rstrip("\n")

    def write(self, secret: str) -> None:
        if not secret:
            self._delete()
            return
        command = f"add-generic-password -U -s {_quoted(self.SERVICE)} -a {_quoted(self._account)} -w {_quoted(secret)}\n"
        done = self._run(["security", "-i"], command)
        if done.returncode != 0 or self.read() != secret:
            raise SecretStoreError(f"The keychain did not keep the token: {done.stderr.strip()}")

    def _delete(self) -> None:
        done = self._run(["security", "delete-generic-password", "-s", self.SERVICE, "-a", self._account], None)
        if done.returncode not in (0, self.NOT_FOUND):
            raise SecretStoreError(f"The keychain did not forget the token: {done.stderr.strip()}")


def _quoted(value: str) -> str:
    if any(char in value for char in '"\\\n'):
        raise SecretStoreError("The keychain cannot keep a value with quotes, backslashes or line breaks")
    return f'"{value}"'


def platform_secret(data_dir: Path) -> SecretStore:
    if sys.platform == "darwin":
        return KeychainSecret(data_dir)
    log.warning("No keychain on this platform: the phone page token lives only until the app stops")
    return MemorySecret()
