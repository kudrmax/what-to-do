"""Finding a program the user installed: PATH first, then the folders installers use."""

from __future__ import annotations

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tests.helpers import fake_program
from where_to_go.claude_login import claude_cli, claude_places
from where_to_go import installed_cli
from where_to_go.installed_cli import CliStatus, InstalledCli
from where_to_go.launcher.tools import Tools

MINIMUM = "2.1.321"
REAL_WHICH = shutil.which


class FakeVersion:
    def __init__(self, answer: str | None = "2.1.325 (Claude Code)") -> None:
        self.answer = answer
        self.calls: list[Path] = []

    def __call__(self, path: Path) -> str | None:
        self.calls.append(path)
        return self.answer


def program(directory: Path) -> Path:
    return fake_program(directory, "print('2.1.330 (Claude Code)')")


def finder(path_dirs: list[Path], extra_dirs: list[Path], version: FakeVersion | None = None) -> InstalledCli:
    environ = {"PATH": os.pathsep.join(str(directory) for directory in path_dirs)}
    return InstalledCli("claude", MINIMUM, extra_dirs=lambda: extra_dirs, environ=environ, run_version=version or FakeVersion())


def test_path_wins_over_fixed_places(tmp_path: Path) -> None:
    on_path = program(tmp_path / "path")
    program(tmp_path / "fixed")

    assert finder([tmp_path / "path"], [tmp_path / "fixed"]).find().path == on_path


def test_fixed_places_when_path_lacks_it(tmp_path: Path) -> None:
    fixed = program(tmp_path / "fixed")

    assert finder([], [tmp_path / "missing", tmp_path / "fixed"]).find().path == fixed


def test_missing(tmp_path: Path) -> None:
    found = finder([tmp_path / "path"], [tmp_path / "fixed"]).find()

    assert found.status == CliStatus.MISSING
    assert found.path is None
    assert found.version is None
    assert found.update_command is None


def test_too_old(tmp_path: Path) -> None:
    program(tmp_path / "fixed")

    found = finder([], [tmp_path / "fixed"], FakeVersion("2.1.200")).find()

    assert found.status == CliStatus.TOO_OLD
    assert found.version == "2.1.200"
    assert found.minimum == MINIMUM


def test_ready(tmp_path: Path) -> None:
    path = program(tmp_path / "fixed")

    found = finder([], [tmp_path / "fixed"], FakeVersion("2.1.325 (Claude Code)\n")).find()

    assert found.status == CliStatus.READY
    assert found.path == path
    assert found.version == "2.1.325"


def test_newer_minor_beats_longer_patch(tmp_path: Path) -> None:
    program(tmp_path / "fixed")

    assert finder([], [tmp_path / "fixed"], FakeVersion("2.2.0")).find().status == CliStatus.READY


def test_unreadable_version_counts_as_too_old(tmp_path: Path) -> None:
    program(tmp_path / "fixed")

    for answer in (None, "garbage"):
        found = finder([], [tmp_path / "fixed"], FakeVersion(answer)).find()

        assert found.status == CliStatus.TOO_OLD
        assert found.version is None


def test_version_cached_until_file_changes(tmp_path: Path) -> None:
    path = program(tmp_path / "fixed")
    version = FakeVersion()
    cli = finder([], [tmp_path / "fixed"], version)

    cli.find()
    cli.find()
    assert len(version.calls) == 1

    moment = path.stat().st_mtime_ns + 10**9
    os.utime(path, ns=(moment, moment))
    cli.find()
    assert len(version.calls) == 2


class AnswersInTurn(FakeVersion):
    def __init__(self, *answers: str | None) -> None:
        super().__init__()
        self.answers = list(answers)

    def __call__(self, path: Path) -> str | None:
        self.calls.append(path)
        return self.answers.pop(0)


def test_a_version_not_given_is_asked_again(tmp_path: Path) -> None:
    program(tmp_path / "fixed")
    version = AnswersInTurn(None, "2.1.325 (Claude Code)")
    cli = finder([], [tmp_path / "fixed"], version)

    assert cli.find().status == CliStatus.TOO_OLD
    found = cli.find()

    assert found.status == CliStatus.READY
    assert found.version == "2.1.325"
    assert len(version.calls) == 2


class SlowVersion(FakeVersion):
    def __call__(self, path: Path) -> str | None:
        time.sleep(0.05)
        return super().__call__(path)


def test_finds_at_once_ask_the_version_once(tmp_path: Path) -> None:
    program(tmp_path / "fixed")
    version = SlowVersion()
    cli = finder([], [tmp_path / "fixed"], version)

    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(lambda _: cli.find().status, range(8)))

    assert statuses == [CliStatus.READY] * 8
    assert len(version.calls) == 1


@pytest.mark.skipif(os.name == "nt", reason="Windows finds programs by their extension, so a link named claude is never a candidate")
def test_broken_symlink_skipped(tmp_path: Path) -> None:
    (tmp_path / "path").mkdir()
    (tmp_path / "path" / "claude").symlink_to(tmp_path / "gone" / "claude")
    real = program(tmp_path / "fixed")

    assert finder([tmp_path / "path"], [tmp_path / "fixed"]).find().path == real


@pytest.mark.skipif(os.name == "nt", reason="Windows files have no executable bit")
def test_non_executable_file_on_path_skipped(tmp_path: Path) -> None:
    plain = program(tmp_path / "path")
    plain.chmod(0o644)
    real = program(tmp_path / "fixed")

    assert finder([tmp_path / "path"], [tmp_path / "fixed"]).find().path == real


class VanishingFirst:
    """`which` names a file that is gone by the time it is looked at, as when `brew upgrade` removes the old version."""

    def __init__(self, gone: Path, times: int) -> None:
        self.gone = gone
        self.times = times

    def __call__(self, name: str, path: str | None = None) -> str | None:
        if self.times > 0:
            self.times -= 1
            return str(self.gone)
        return REAL_WHICH(name, path=path)


def test_program_removed_after_it_was_found_is_looked_up_again(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = program(tmp_path / "fixed")
    monkeypatch.setattr(installed_cli.shutil, "which", VanishingFirst(tmp_path / "old" / "claude", times=1))

    found = finder([], [tmp_path / "fixed"]).find()

    assert found.status == CliStatus.READY
    assert found.path == real


def test_program_that_keeps_vanishing_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installed_cli.shutil, "which", VanishingFirst(tmp_path / "old" / "claude", times=10))

    found = finder([], [tmp_path / "fixed"]).find()

    assert found.status == CliStatus.MISSING
    assert found.path is None


@pytest.mark.skipif(os.name == "nt", reason="Homebrew casks do not exist on Windows")
def test_homebrew_cask_update_command(tmp_path: Path) -> None:
    cask = program(tmp_path / "homebrew" / "Caskroom" / "claude-code@latest" / "2.1.325")
    (tmp_path / "homebrew" / "bin").mkdir()
    (tmp_path / "homebrew" / "bin" / "claude").symlink_to(cask)

    found = finder([tmp_path / "homebrew" / "bin"], []).find()

    assert found.update_command == "brew upgrade --cask claude-code@latest"


def test_other_install_update_command(tmp_path: Path) -> None:
    program(tmp_path / "local" / "bin")

    assert finder([], [tmp_path / "local" / "bin"]).find().update_command == "claude update"


def test_default_version_runner_asks_the_program(tmp_path: Path) -> None:
    program(tmp_path / "fixed")

    found = InstalledCli("claude", MINIMUM, extra_dirs=lambda: [tmp_path / "fixed"], environ={**os.environ, "PATH": ""}).find()

    assert found.status == CliStatus.READY
    assert found.version == "2.1.330"


def test_claude_searches_the_native_installer_folder(tmp_path: Path) -> None:
    native = program(tmp_path / ".local" / "bin")

    found = claude_cli(environ={"PATH": ""}, home=tmp_path).find()

    assert found.path == native
    assert found.minimum == MINIMUM


def test_claude_places_in_installer_order_then_npm_folders(tmp_path: Path) -> None:
    (tmp_path / ".nvm" / "versions" / "node" / "v22.3.0" / "bin").mkdir(parents=True)

    places = claude_places({}, tmp_path)

    assert places[:4] == [tmp_path / ".local" / "bin", Path("/opt/homebrew/bin"), Path("/usr/local/bin"), tmp_path / ".claude" / "local"]
    assert places[-2:] == [tmp_path / ".volta" / "bin", tmp_path / ".nvm" / "versions" / "node" / "v22.3.0" / "bin"]
    assert len(places) == len(set(places))


@pytest.mark.skipif(os.name != "nt", reason="program extensions from PATHEXT exist on Windows only")
def test_claude_finds_the_native_installers_exe_before_an_npm_shim(tmp_path: Path) -> None:
    native = tmp_path / ".local" / "bin" / "claude.exe"
    native.parent.mkdir(parents=True)
    native.write_bytes(b"")
    (native.parent / "claude.cmd").write_text("@echo 2.1.330\n", encoding="utf-8")

    found = claude_cli(environ={**os.environ, "PATH": ""}, home=tmp_path).find()

    assert found.path == native
    assert found.update_command == "claude update"


def test_program_dirs_lists_nvm_and_volta(tmp_path: Path) -> None:
    for version in ("v18.20.0", "v22.3.0", "v20.11.1"):
        (tmp_path / ".nvm" / "versions" / "node" / version / "bin").mkdir(parents=True)

    dirs = Tools(environ={}, home=tmp_path).program_dirs()

    assert tmp_path / ".volta" / "bin" in dirs
    nvm = [directory for directory in dirs if ".nvm" in directory.parts]
    assert nvm == [tmp_path / ".nvm" / "versions" / "node" / version / "bin" for version in ("v22.3.0", "v20.11.1", "v18.20.0")]
