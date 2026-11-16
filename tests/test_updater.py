"""The updater against a local origin: fetch the tags, stop the app, check out the newest release, install,
build, start the app again as it ran. Also the Update button's path to it: the app's runner starting it."""

from __future__ import annotations

import json
import plistlib
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil
import pytest

from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.macos_apps import MacApps
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.processes import find_process
from where_to_go.launcher.updater import START, UpdateLog, Updater
from where_to_go.releases import AppVersion, GitReleases
from where_to_go.updating import UpdateFiles, UpdateRunner, UpdateState

ROOT = Path(__file__).resolve().parents[1]
FAKES = Path(__file__).parent / "fakes"
FAKE_CLI = str(FAKES / "fake_cli.py")
FAKE_UPDATE = str(FAKES / "fake_update.py")
STATUS_SERVER = ROOT / "scripts" / "update_status_server.py"
IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
WAIT_S = 30
UPDATES_IN_A_ROW = 5
HOST = "127.0.0.1"
CHECK = "Checking for a new version"
ALL_DONE = [
    ("done", "Downloading v1.1.0"),
    ("done", "Installing v1.1.0"),
    ("done", START),
]
GITIGNORE = "data/\n.pids/\n.logs/\n"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port: int = probe.getsockname()[1]
        return port


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def wait_for(condition: Callable[[], bool], timeout: float = WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


@dataclass(frozen=True)
class Copy:
    root: Path
    publisher: Path
    calls_file: Path
    flags: Path
    apps_dir: Path
    port: int

    def release(self, version: str, *, macos_change: bool = False) -> None:
        (self.publisher / "VERSION").write_text(version)
        if macos_change:
            app_file = self.publisher / "macos" / "Sources" / "App.swift"
            app_file.parent.mkdir(parents=True, exist_ok=True)
            app_file.write_text(f"// {version}\n")
        git(self.publisher, "add", "-A")
        git(self.publisher, "commit", "-m", version)
        git(self.publisher, "tag", f"v{version}")
        git(self.publisher, "push", "--quiet", "origin", "HEAD", "--tags")

    def flag(self, name: str, value: str = "") -> None:
        (self.flags / name).write_text(value)

    def updater(self, root: Path | None = None) -> Updater:
        paths = ProjectPaths(root or self.root)
        config = InstanceConfig(port=self.port, data_dir=paths.root / "data", instance="prod", menu_bar_icon=False)
        return Updater(
            paths,
            config,
            UpdateLog(paths.update_log, echo=None),
            cli=[sys.executable, FAKE_CLI],
            package_sync=[sys.executable, FAKE_CLI, "sync"],
            apps=MacApps(self.apps_dir),
            macos=True,
            app_builder=[sys.executable, FAKE_CLI, "app"],
        )

    def run(self, root: Path | None = None) -> int:
        return self.updater(root).run()

    def start(self) -> tuple[threading.Thread, list[int]]:
        codes: list[int] = []
        thread = threading.Thread(target=lambda: codes.append(self.run()))
        thread.start()
        return thread, codes

    def calls(self) -> list[str]:
        return self.calls_file.read_text().splitlines() if self.calls_file.exists() else []

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def tag_commit(self, tag: str) -> str:
        return git(self.root, "rev-parse", f"{tag}^{{commit}}")

    def state(self) -> str:
        return (self.root / UpdateFiles.STATE).read_text().strip()

    def error(self) -> str:
        return (self.root / UpdateFiles.ERROR).read_text()

    def log(self) -> str:
        path = self.root / UpdateFiles.LOG
        return path.read_text() if path.exists() else ""

    def progress(self) -> list[tuple[str, str]]:
        text = (self.root / UpdateFiles.PROGRESS).read_text()
        parts = (line.partition("\t") for line in text.splitlines())
        return [(status, title) for status, _, title in parts]

    def get(self, path: str) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{self.port}{path}", timeout=WAIT_S) as response:  # noqa: S310
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, ""

    def status_server_listens(self) -> bool:
        with socket.socket() as probe:
            return probe.connect_ex((HOST, self.port)) == 0

    def install_app(self, project_dir: Path) -> None:
        contents = self.apps_dir / "What To Do.app" / "Contents"
        contents.mkdir(parents=True)
        with (contents / "Info.plist").open("wb") as plist:
            plistlib.dump({"WTGProjectDir": str(project_dir)}, plist)


@pytest.fixture
def copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Copy:
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=master", str(bare))
    publisher = tmp_path / "publisher"
    git(tmp_path, "clone", "--quiet", str(bare), str(publisher))
    git(publisher, "checkout", "--quiet", "-b", "master")
    (publisher / ".gitignore").write_text(GITIGNORE)
    (publisher / "scripts").mkdir()
    shutil.copy(STATUS_SERVER, publisher / "scripts" / STATUS_SERVER.name)
    flags = tmp_path / "flags"
    flags.mkdir()
    result = Copy(
        root=tmp_path / "installed",
        publisher=publisher,
        calls_file=tmp_path / "calls.txt",
        flags=flags,
        apps_dir=tmp_path / "Applications",
        port=free_port(),
    )
    server = {"port": result.port, "data_dir": str(tmp_path / "data"), "ui": str(result.root / "frontend" / "dist"), "instance": "prod"}
    result.flag("servers.json", json.dumps({"servers": [server]}))
    result.release("1.0.0")
    git(tmp_path, "clone", "--quiet", str(bare), str(result.root))
    for name, value in {"CALLS": str(result.calls_file), "FLAGS": str(flags), "UPDATE_APPS_DIR": str(result.apps_dir)}.items():
        monkeypatch.setenv(name, value)
    return result


UPDATE_CALLS = ["down", "sync", "build", "up 1.1.0"]


def test_moves_to_the_highest_release_tag_and_restarts_what_ran(copy: Copy) -> None:
    git(copy.root, "checkout", "--quiet", "v1.0.0")
    copy.release("1.2.0")
    copy.release("1.10.0")
    git(copy.publisher, "tag", "v2.0.0-rc1")
    git(copy.publisher, "push", "--quiet", "origin", "--tags")

    assert copy.run() == 0, copy.log()

    assert copy.head() == copy.tag_commit("v1.10.0")
    assert copy.calls() == ["down", "sync", "build", "up 1.10.0"]
    assert copy.state() == "done"


def test_a_copy_that_was_not_running_is_updated_and_left_stopped(copy: Copy) -> None:
    copy.flag("servers.json", '{"servers": []}')
    copy.release("1.1.0")

    assert copy.run() == 0, copy.log()

    assert copy.calls() == ["down", "sync"]
    assert "Start it with: where-to-go up" in copy.log()
    assert copy.progress() == ALL_DONE


def test_head_ahead_of_the_latest_tag_is_left_as_it_is(copy: Copy) -> None:
    (copy.publisher / "unreleased.txt").write_text("work in progress")
    git(copy.publisher, "add", "-A")
    git(copy.publisher, "commit", "-m", "unreleased")
    git(copy.publisher, "push", "--quiet", "origin", "HEAD")
    git(copy.root, "pull", "--quiet", "--ff-only")
    head = copy.head()

    assert copy.run() == 0, copy.log()

    assert "Already up to date" in copy.log()
    assert copy.head() == head
    assert copy.calls() == []
    assert copy.state() == "done"


def test_a_failed_start_stops_there_and_says_which_step_it_was(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("fail_up", "1.1.0")

    assert copy.run() == 1

    assert copy.calls() == UPDATE_CALLS
    assert copy.head() == copy.tag_commit("v1.1.0")
    assert copy.state() == "failed"
    assert "Couldn't start the new version" in copy.error()
    assert "broke" in copy.log()


def test_a_failed_install_stops_before_the_start(copy: Copy) -> None:
    copy.release("1.1.0")
    updater = copy.updater()
    updater._package_sync = [sys.executable, "-c", "import sys; print('no network'); sys.exit(1)"]

    assert updater.run() == 1

    assert copy.calls() == ["down"]
    assert "uv sync" in copy.error()
    assert copy.progress()[-1] == ("failed", "Installing v1.1.0")
    assert not copy.status_server_listens()


def test_unreachable_origin_fails_without_touching_the_copy(copy: Copy) -> None:
    head = copy.head()
    git(copy.root, "remote", "set-url", "origin", str(copy.root.parent / "nowhere.git"))

    assert copy.run() == 1

    assert "Couldn't reach GitHub" in copy.error()
    assert copy.head() == head
    assert copy.calls() == []
    assert copy.state() == "failed"
    assert copy.progress() == [("failed", CHECK)]


def test_uncommitted_changes_refuse_the_update(copy: Copy) -> None:
    copy.release("1.1.0")
    (copy.root / "VERSION").write_text("edited")

    assert copy.run() == 1

    assert "VERSION" in copy.log()
    assert "uncommitted changes" in copy.error()
    assert copy.calls() == []
    assert copy.state() == "failed"


def test_worktree_refuses_the_update(copy: Copy, tmp_path: Path) -> None:
    copy.release("1.1.0")
    linked = tmp_path / "linked"
    git(copy.root, "worktree", "add", "--quiet", str(linked), "HEAD")

    assert copy.run(linked) == 1

    assert (linked / UpdateFiles.STATE).read_text() == "failed"
    assert "main copy" in (linked / UpdateFiles.ERROR).read_text()
    assert copy.calls() == []


def test_every_run_is_logged_under_its_own_header(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.run()
    copy.run()

    log = copy.log()
    assert log.startswith("=== update ")
    assert log.count("=== update ") == 2
    assert "Updated to v1.1.0." in log
    assert "Already up to date (v1.1.0)." in log


def test_a_tag_moved_on_origin_does_not_stop_the_update(copy: Copy) -> None:
    copy.release("1.1.0")
    assert copy.run() == 0
    (copy.publisher / "notes.txt").write_text("moved")
    git(copy.publisher, "add", "-A")
    git(copy.publisher, "commit", "-m", "moved")
    git(copy.publisher, "tag", "--force", "v1.1.0")
    git(copy.publisher, "push", "--quiet", "--force", "origin", "HEAD", "--tags")
    copy.release("1.2.0")

    assert copy.run() == 0, copy.log()

    assert copy.head() == copy.tag_commit("v1.2.0")


def test_app_of_this_copy_is_rebuilt_when_its_code_changed(copy: Copy) -> None:
    copy.install_app(copy.root)
    copy.release("1.1.0", macos_change=True)

    assert copy.run() == 0, copy.log()

    assert copy.calls() == ["down", "app", "sync", "build", "up 1.1.0"]


def test_app_is_not_rebuilt_when_its_code_did_not_change(copy: Copy) -> None:
    copy.install_app(copy.root)
    copy.release("1.1.0")

    assert copy.run() == 0, copy.log()

    assert "app" not in copy.calls()


def test_app_of_another_copy_is_not_rebuilt(copy: Copy, tmp_path: Path) -> None:
    other = tmp_path / "other-copy"
    other.mkdir()
    copy.install_app(other)
    copy.release("1.1.0", macos_change=True)

    assert copy.run() == 0, copy.log()

    assert "app" not in copy.calls()


def test_second_update_at_the_same_time_refuses_and_leaves_the_first_alone(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("hold", "hold")
    first, codes = copy.start()
    try:
        wait_for(lambda: "down" in copy.calls())

        assert copy.run() == 1

        assert "already running" in copy.log()
        assert copy.state() == "running"
    finally:
        copy.flag("hold", "go")
        first.join(WAIT_S)
    assert codes == [0]
    assert copy.state() == "done"
    assert copy.calls() == UPDATE_CALLS


def test_script_and_release_source_pick_the_same_latest_tag(copy: Copy) -> None:
    copy.release("1.2.0")
    copy.release("1.10.0")
    git(copy.publisher, "tag", "v2.0.0-rc1")
    git(copy.publisher, "tag", "not-a-release")
    git(copy.publisher, "push", "--quiet", "origin", "--tags")
    git(copy.root, "checkout", "--quiet", "v1.0.0")

    assert copy.run() == 0, copy.log()

    assert copy.head() == copy.tag_commit("v1.10.0")
    assert GitReleases(copy.root).latest() == AppVersion(1, 10, 0)


def test_progress_names_every_stage_of_a_successful_update(copy: Copy) -> None:
    copy.release("1.1.0")

    assert copy.run() == 0, copy.log()

    assert copy.progress() == ALL_DONE


def test_a_failed_start_marks_its_stage(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("fail_up", "1.1.0")

    copy.run()

    assert copy.progress() == [
        ("done", "Downloading v1.1.0"),
        ("done", "Installing v1.1.0"),
        ("failed", START),
    ]
    assert not copy.status_server_listens()


def test_nothing_newer_ends_the_check_done(copy: Copy) -> None:
    copy.run()

    assert copy.progress() == [("done", CHECK)]


def test_status_server_answers_while_the_app_is_stopped(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("hold_up", "hold")
    update, codes = copy.start()
    try:
        wait_for(copy.status_server_listens)
        wait_for(lambda: ("current", START) in copy.progress())

        state_status, body = copy.get("/api/update/state")
        version_status, _ = copy.get("/api/version")
    finally:
        copy.flag("hold_up", "go")
        update.join(WAIT_S)

    assert state_status == 200
    assert json.loads(body) == {
        "state": "running",
        "log_tail": "",
        "steps": [
            {"title": "Downloading v1.1.0", "status": "done"},
            {"title": "Installing v1.1.0", "status": "done"},
            {"title": START, "status": "current"},
        ],
    }
    assert version_status == 503
    assert codes == [0]
    assert not copy.status_server_listens()


def test_status_server_shows_the_start_until_up_takes_the_port(copy: Copy) -> None:
    copy.release("1.1.0")

    assert copy.run() == 0, copy.log()

    saw = (copy.flags / "up_saw").read_text().splitlines()
    assert saw == [f"alive current\t{START}"]
    assert not (copy.root / ".pids" / f"update_status-{copy.port}.pid").exists()


def test_update_goes_on_when_the_status_server_cannot_start(copy: Copy) -> None:
    copy.release("1.1.0")
    updater = copy.updater()
    updater._status._python = str(copy.root / "no-such-python")

    assert updater.run() == 0, copy.log()

    assert copy.progress() == ALL_DONE


@pytest.fixture
def button(copy: Copy) -> UpdateRunner:
    """The Update button: the app's runner starting the updater as a process of its own."""
    return UpdateRunner(
        copy.root,
        command=[sys.executable, FAKE_UPDATE, "--background"],
        is_update=lambda cmdline: any(part.endswith("fake_update.py") for part in cmdline) and "update" in cmdline,
    )


def press(button: UpdateRunner) -> UpdateState:
    button.start()
    deadline = time.monotonic() + WAIT_S
    while (state := button.progress().state) is UpdateState.RUNNING:
        assert time.monotonic() < deadline, "the update never ended"
        time.sleep(0.05)
    return state


def test_the_button_updates_many_times_in_a_row(copy: Copy, button: UpdateRunner) -> None:
    for minor in range(1, UPDATES_IN_A_ROW + 1):
        copy.release(f"1.{minor}.0")

        assert press(button) is UpdateState.DONE, copy.log()
        assert copy.head() == copy.tag_commit(f"v1.{minor}.0")


def test_the_button_works_after_a_failed_update(copy: Copy, button: UpdateRunner) -> None:
    copy.release("1.1.0")
    copy.flag("fail_up", "1.1.0")
    assert press(button) is UpdateState.FAILED
    copy.flag("fail_up", "")
    copy.release("1.2.0")

    assert press(button) is UpdateState.DONE, copy.log()
    assert copy.head() == copy.tag_commit("v1.2.0")


def test_the_button_works_after_the_update_was_killed(copy: Copy, button: UpdateRunner) -> None:
    copy.release("1.1.0")
    copy.flag("hold", "hold")
    button.start()
    wait_for(lambda: "down" in copy.calls())
    updater = find_process(int((copy.root / UpdateFiles.PID).read_text()))
    assert updater is not None
    updater.kill()
    updater.wait(WAIT_S)
    copy.flag("hold", "go")
    wait_for(lambda: button.progress().state is UpdateState.FAILED)

    assert press(button) is UpdateState.DONE, copy.log()


def test_the_update_outlives_the_process_that_started_it(copy: Copy, button: UpdateRunner) -> None:
    """The app stops itself during the update: the update must not be among the processes it started."""
    copy.release("1.1.0")
    copy.flag("hold", "hold")
    button.start()
    wait_for(lambda: "down" in copy.calls())
    updater = find_process(int((copy.root / UpdateFiles.PID).read_text()))
    try:
        assert updater is not None
        assert updater.pid not in {child.pid for child in psutil.Process().children(recursive=True)}
    finally:
        copy.flag("hold", "go")
    wait_for(lambda: button.progress().state is UpdateState.DONE)


def test_the_button_never_waits_for_a_git_password(copy: Copy, button: UpdateRunner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GIT_TERMINAL_PROMPT", raising=False)
    copy.release("1.1.0")

    assert press(button) is UpdateState.DONE, copy.log()
    assert (copy.flags / "sync_environment").read_text() == "GIT_TERMINAL_PROMPT=0 stdin=empty"
