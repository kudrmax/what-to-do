"""`make update` against a local origin: git fetch, make down, git checkout <tag>, make up.
Also the Update button's path to it: the app's runner starting the same script."""

from __future__ import annotations

import json
import os
import plistlib
import shlex
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from where_to_go.releases import AppVersion, GitReleases
from where_to_go.updating import (
    UpdateAlreadyRunningError,
    UpdateFiles,
    UpdateRunner,
    UpdateState,
    UpdateStep,
    UpdateStepStatus,
)

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "update.sh"
IDENTITY = ["-c", "user.name=Test", "-c", "user.email=test@example.com"]
# Generous for a run of the fake Makefile; a hang fails the test instead of the suite.
WAIT_S = 20
# How many updates in a row the Update button must carry out.
UPDATES_IN_A_ROW = 5

# Every target records itself. `up` leaves the copy's processes running and `down` stops
# them. Files in FLAGS switch behaviour on: fail_up (fails on the version written in it),
# hold makes `down` wait while it says "hold", hold_up makes `up` wait while it says "hold"
# before it touches anything, spawn makes `up` leave a real background process, as the
# servers do. `up` stops the update's status server by its pid file, as the real one does,
# and records in up_saw whether it was still alive and which stage was current; it fails
# when something still listens on the port.
FAKE_MAKEFILE = """\
VERSION := $(shell cat VERSION)
STATUS_PID := .pids/update_status.pid

down:
\t@echo $@ >> $(CALLS)
\t@while [ "$$(cat $(FLAGS)/hold 2>/dev/null)" = hold ]; do sleep 0.05; done
\t@echo stopped > $(FLAGS)/processes

app:
\t@echo $@ >> $(CALLS)

up:
\t@while [ "$$(cat $(FLAGS)/hold_up 2>/dev/null)" = hold ]; do sleep 0.05; done
\t@echo "up $(VERSION)" >> $(CALLS)
\t@pid=$$(cat $(STATUS_PID) 2>/dev/null); \\
\tif [ -n "$$pid" ] && ps -o command= -p $$pid | grep -q update_status_server; then \\
\t    echo "alive $$(grep current .pids/update.progress)" >> $(FLAGS)/up_saw; \\
\t    kill $$pid; \\
\t    while ps -o command= -p $$pid | grep -q update_status_server; do sleep 0.05; done; \\
\t    rm -f $(STATUS_PID); \\
\telse echo gone >> $(FLAGS)/up_saw; fi
\t@python3 -c "$$PORT_FREE_CHECK" || { echo "port busy"; exit 1; }
\t@echo running > $(FLAGS)/processes
\t@if [ -f $(FLAGS)/spawn ]; then sleep 30 </dev/null >/dev/null 2>&1 & fi
\t@if [ "$$(cat $(FLAGS)/fail_up 2>/dev/null)" = "$(VERSION)" ]; then echo broke; exit 1; fi
"""

# Binds the status server's port the way uvicorn does, with SO_REUSEADDR.
PORT_FREE_CHECK = (
    "import os, socket; s = socket.socket(); "
    "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); "
    "s.bind((os.environ['UPDATE_STATUS_HOST'], int(os.environ['UPDATE_STATUS_PORT'])))"
)
STATUS_HOST = "127.0.0.1"
CHECK = "Ищем новую версию"
START = "Запускаем новую версию"
ALL_DONE = [
    ("done", "Скачиваем v1.1.0"),
    ("done", "Устанавливаем v1.1.0"),
    ("done", START),
]
GITIGNORE = "data/\n.pids/\n.logs/\n"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((STATUS_HOST, 0))
        port: int = probe.getsockname()[1]
        return port


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@dataclass(frozen=True)
class Copy:
    root: Path
    publisher: Path
    calls_file: Path
    flags: Path
    apps_dir: Path
    status_port: int

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

    def env(self) -> dict[str, str]:
        env = {**os.environ, **self.extra_env()}
        env.pop("MAKEFLAGS", None)
        env.pop("MAKELEVEL", None)
        return env

    def extra_env(self) -> dict[str, str]:
        return {
            "CALLS": str(self.calls_file),
            "FLAGS": str(self.flags),
            "UPDATE_APPS_DIR": str(self.apps_dir),
            "MAKE": "make",
            "UPDATE_STATUS_PORT": str(self.status_port),
            "UPDATE_STATUS_HOST": STATUS_HOST,
            "PORT_FREE_CHECK": PORT_FREE_CHECK,
        }

    def start(self) -> subprocess.Popen[str]:
        return subprocess.Popen(
            ["/bin/bash", str(SCRIPT)], cwd=self.root, env=self.env(),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )

    def run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", str(SCRIPT)], cwd=self.root, env=self.env(), capture_output=True, text=True, timeout=WAIT_S,
        )

    def calls(self) -> list[str]:
        if not self.calls_file.exists():
            return []
        return self.calls_file.read_text().splitlines()

    def head(self) -> str:
        return git(self.root, "rev-parse", "HEAD")

    def tag_commit(self, tag: str) -> str:
        return git(self.root, "rev-parse", f"{tag}^{{commit}}")

    def state(self) -> str:
        return (self.root / UpdateFiles.STATE).read_text().strip()

    def error(self) -> str:
        return (self.root / UpdateFiles.ERROR).read_text()

    def log(self) -> str:
        return (self.root / UpdateFiles.LOG).read_text()

    def progress(self) -> list[tuple[str, str]]:
        text = (self.root / UpdateFiles.PROGRESS).read_text()
        parts = (line.partition("\t") for line in text.splitlines())
        return [(status, title) for status, _, title in parts]

    def get(self, path: str) -> tuple[int, str]:
        url = f"http://{STATUS_HOST}:{self.status_port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=WAIT_S) as response:  # noqa: S310
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, ""

    def status_server_listens(self) -> bool:
        with socket.socket() as probe:
            return probe.connect_ex((STATUS_HOST, self.status_port)) == 0

    def install_app(self, project_dir: Path) -> None:
        contents = self.apps_dir / "What To Do.app" / "Contents"
        contents.mkdir(parents=True)
        with (contents / "Info.plist").open("wb") as plist:
            plistlib.dump({"WTGProjectDir": str(project_dir)}, plist)


@pytest.fixture
def copy(tmp_path: Path) -> Copy:
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "--quiet", "--bare", "--initial-branch=master", str(bare))
    publisher = tmp_path / "publisher"
    git(tmp_path, "clone", "--quiet", str(bare), str(publisher))
    git(publisher, "checkout", "--quiet", "-b", "master")
    (publisher / "Makefile").write_text(FAKE_MAKEFILE)
    (publisher / ".gitignore").write_text(GITIGNORE)
    flags = tmp_path / "flags"
    flags.mkdir()
    result = Copy(
        root=tmp_path / "installed",
        publisher=publisher,
        calls_file=tmp_path / "calls.txt",
        flags=flags,
        apps_dir=tmp_path / "Applications",
        status_port=free_port(),
    )
    result.flag("processes", "running")
    result.release("1.0.0")
    git(tmp_path, "clone", "--quiet", str(bare), str(result.root))
    return result


def _wait_for(condition: Callable[[], bool], timeout: float = WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def test_moves_to_the_highest_release_tag_and_starts(copy: Copy) -> None:
    git(copy.root, "checkout", "--quiet", "v1.0.0")
    copy.release("1.2.0")
    copy.release("1.10.0")
    git(copy.publisher, "tag", "v2.0.0-rc1")
    git(copy.publisher, "push", "--quiet", "origin", "--tags")

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert copy.head() == copy.tag_commit("v1.10.0")
    assert copy.calls() == ["down", "up 1.10.0"]
    assert copy.state() == "done"


def test_head_ahead_of_the_latest_tag_is_left_as_it_is(copy: Copy) -> None:
    (copy.publisher / "unreleased.txt").write_text("work in progress")
    git(copy.publisher, "add", "-A")
    git(copy.publisher, "commit", "-m", "unreleased")
    git(copy.publisher, "push", "--quiet", "origin", "HEAD")
    git(copy.root, "pull", "--quiet", "--ff-only")
    head = copy.head()

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert "Already up to date" in copy.log()
    assert copy.head() == head
    assert copy.calls() == []
    assert copy.state() == "done"


def test_a_failed_start_stops_there_and_says_which_step_it_was(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("fail_up", "1.1.0")

    result = copy.run()

    assert result.returncode == 1
    assert copy.calls() == ["down", "up 1.1.0"]
    assert copy.head() == copy.tag_commit("v1.1.0")
    assert copy.state() == "failed"
    assert "(make up)" in copy.error()
    assert "broke" in copy.log()


def test_unreachable_origin_fails_without_touching_the_copy(copy: Copy) -> None:
    head = copy.head()
    git(copy.root, "remote", "set-url", "origin", str(copy.root.parent / "nowhere.git"))

    result = copy.run()

    assert result.returncode == 1
    assert "Не получилось связаться с GitHub" in copy.error()
    assert copy.head() == head
    assert copy.calls() == []
    assert copy.state() == "failed"


def test_uncommitted_changes_refuse_the_update(copy: Copy) -> None:
    copy.release("1.1.0")
    (copy.root / "VERSION").write_text("edited")

    result = copy.run()

    assert result.returncode == 1
    assert "VERSION" in copy.log()
    assert "незакоммиченные изменения" in copy.error()
    assert copy.calls() == []
    assert copy.state() == "failed"


def test_worktree_refuses_the_update(copy: Copy, tmp_path: Path) -> None:
    copy.release("1.1.0")
    linked = tmp_path / "linked"
    git(copy.root, "worktree", "add", "--quiet", str(linked), "HEAD")

    result = subprocess.run(["/bin/bash", str(SCRIPT)], cwd=linked, env=copy.env(), capture_output=True, text=True)

    assert result.returncode == 1
    assert (linked / UpdateFiles.STATE).read_text() == "failed"
    assert "основной копии" in (linked / UpdateFiles.ERROR).read_text()
    assert copy.calls() == []


def test_every_run_is_logged_under_its_own_header(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.run()
    copy.run()

    log = copy.log()
    assert log.startswith(f"{UpdateFiles.RUN_HEADER} ")
    assert log.count(f"{UpdateFiles.RUN_HEADER} ") == 2
    assert "Updated to v1.1.0." in log
    assert "Already up to date (v1.1.0)." in log


def test_a_tag_moved_on_origin_does_not_stop_the_update(copy: Copy) -> None:
    copy.release("1.1.0")
    assert copy.run().returncode == 0
    (copy.publisher / "notes.txt").write_text("moved")
    git(copy.publisher, "add", "-A")
    git(copy.publisher, "commit", "-m", "moved")
    git(copy.publisher, "tag", "--force", "v1.1.0")
    git(copy.publisher, "push", "--quiet", "--force", "origin", "HEAD", "--tags")
    copy.release("1.2.0")

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert copy.head() == copy.tag_commit("v1.2.0")


def test_app_of_this_copy_is_rebuilt_when_its_code_changed(copy: Copy) -> None:
    copy.install_app(copy.root)
    copy.release("1.1.0", macos_change=True)

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert copy.calls() == ["down", "app", "up 1.1.0"]


def test_app_is_not_rebuilt_when_its_code_did_not_change(copy: Copy) -> None:
    copy.install_app(copy.root)
    copy.release("1.1.0")

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert "app" not in copy.calls()


def test_app_of_another_copy_is_not_rebuilt(copy: Copy, tmp_path: Path) -> None:
    other = tmp_path / "other-copy"
    other.mkdir()
    copy.install_app(other)
    copy.release("1.1.0", macos_change=True)

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert "app" not in copy.calls()


def test_second_update_at_the_same_time_refuses_and_leaves_the_first_alone(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("hold", "hold")
    first = copy.start()
    try:
        _wait_for(lambda: "down" in copy.calls())

        second = copy.run()

        assert second.returncode == 1
        assert "already running" in copy.log()
        assert copy.state() == "running"
    finally:
        copy.flag("hold", "go")
        first.wait(timeout=WAIT_S)
    assert first.returncode == 0
    assert copy.state() == "done"
    assert copy.calls() == ["down", "up 1.1.0"]


def test_the_pid_of_a_dead_run_does_not_block(copy: Copy) -> None:
    dead = subprocess.Popen(["/bin/bash", "-c", "exit 0", "update.sh"])
    dead.wait()
    (copy.root / ".pids").mkdir()
    (copy.root / UpdateFiles.PID).write_text(str(dead.pid))
    copy.release("1.1.0")

    result = copy.run()

    assert result.returncode == 0, copy.log()


def test_script_and_release_source_pick_the_same_latest_tag(copy: Copy) -> None:
    copy.release("1.2.0")
    copy.release("1.10.0")
    git(copy.publisher, "tag", "v2.0.0-rc1")
    git(copy.publisher, "tag", "not-a-release")
    git(copy.publisher, "push", "--quiet", "origin", "--tags")
    git(copy.root, "checkout", "--quiet", "v1.0.0")

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert copy.head() == copy.tag_commit("v1.10.0")
    assert GitReleases(copy.root).latest() == AppVersion(1, 10, 0)


def test_progress_names_every_stage_of_a_successful_update(copy: Copy) -> None:
    copy.release("1.1.0")

    result = copy.run()

    assert result.returncode == 0, copy.log()
    assert copy.progress() == ALL_DONE


def test_a_failed_start_marks_its_stage(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("fail_up", "1.1.0")

    copy.run()

    assert copy.progress() == [
        ("done", "Скачиваем v1.1.0"),
        ("done", "Устанавливаем v1.1.0"),
        ("failed", START),
    ]
    assert not copy.status_server_listens()


def test_unreachable_origin_marks_the_check_failed(copy: Copy) -> None:
    git(copy.root, "remote", "set-url", "origin", str(copy.root.parent / "nowhere.git"))

    copy.run()

    assert copy.progress() == [("failed", CHECK)]


def test_nothing_newer_ends_the_check_done(copy: Copy) -> None:
    copy.run()

    assert copy.progress() == [("done", CHECK)]


def test_status_server_answers_while_the_app_is_stopped(copy: Copy) -> None:
    copy.release("1.1.0")
    copy.flag("hold_up", "hold")
    update = copy.start()
    try:
        _wait_for(copy.status_server_listens)
        _wait_for(lambda: ("current", START) in copy.progress())

        state_status, body = copy.get("/api/update/state")
        version_status, _ = copy.get("/api/version")
    finally:
        copy.flag("hold_up", "go")
        update.wait(timeout=WAIT_S)

    assert state_status == 200
    assert json.loads(body) == {
        "state": "running",
        "log_tail": "",
        "steps": [
            {"title": "Скачиваем v1.1.0", "status": "done"},
            {"title": "Устанавливаем v1.1.0", "status": "done"},
            {"title": START, "status": "current"},
        ],
    }
    assert version_status == 503
    assert update.returncode == 0
    assert not copy.status_server_listens()


def test_status_server_shows_the_start_until_make_up_takes_the_port(copy: Copy) -> None:
    copy.release("1.1.0")

    result = copy.run()

    assert result.returncode == 0, copy.log()
    saw = (copy.flags / "up_saw").read_text().splitlines()
    assert saw == [f"alive current\t{START}"]
    assert not (copy.root / ".pids" / "update_status.pid").exists()


def test_update_goes_on_when_the_status_server_cannot_start(copy: Copy) -> None:
    copy.release("1.1.0")
    env = {**copy.env(), "UPDATE_STATUS_PYTHON": "/nonexistent/python3"}

    result = subprocess.run(["/bin/bash", str(SCRIPT)], cwd=copy.root, env=env, capture_output=True, text=True)

    assert result.returncode == 0, copy.log()
    assert copy.progress() == ALL_DONE


@pytest.fixture
def button(copy: Copy, monkeypatch: pytest.MonkeyPatch) -> UpdateRunner:
    """The Update button: the app's runner starting the real script in the copy."""
    for name, value in copy.extra_env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("MAKEFLAGS", raising=False)
    monkeypatch.delenv("MAKELEVEL", raising=False)
    return UpdateRunner(copy.root, str(SCRIPT))


def _press(button: UpdateRunner) -> UpdateState:
    button.start()
    deadline = time.monotonic() + WAIT_S
    while (state := button.progress().state) is UpdateState.RUNNING:
        assert time.monotonic() < deadline, "the update never ended"
        time.sleep(0.05)
    return state


def test_the_button_updates_many_times_in_a_row(copy: Copy, button: UpdateRunner) -> None:
    """Each update leaves servers running, as the real `make up` does; none of them may keep
    the next update from starting."""
    copy.flag("spawn")
    for minor in range(1, UPDATES_IN_A_ROW + 1):
        copy.release(f"1.{minor}.0")

        assert _press(button) is UpdateState.DONE, copy.log()
        assert copy.head() == copy.tag_commit(f"v1.{minor}.0")


def test_the_button_works_after_a_failed_update(copy: Copy, button: UpdateRunner) -> None:
    copy.release("1.1.0")
    copy.flag("fail_up", "1.1.0")
    assert _press(button) is UpdateState.FAILED
    copy.flag("fail_up", "")
    copy.release("1.2.0")

    assert _press(button) is UpdateState.DONE, copy.log()
    assert copy.head() == copy.tag_commit("v1.2.0")


def test_the_button_works_after_the_update_was_killed(copy: Copy, button: UpdateRunner) -> None:
    copy.release("1.1.0")
    copy.flag("hold", "hold")
    button.start()
    _wait_for(lambda: "down" in copy.calls())
    os.kill(int((copy.root / UpdateFiles.PID).read_text()), 9)
    copy.flag("hold", "go")
    _wait_for(lambda: button.progress().state is UpdateState.FAILED)

    assert _press(button) is UpdateState.DONE, copy.log()
    assert copy.head() == copy.tag_commit("v1.1.0")


# The runner on its own, with a stand-in script.

# The stand-in's name: the runner knows a running update by it.
STAND_IN = "update.sh"
# Outlives any test: only the test may end it.
LONG_S = 600


def _wait_for_text(path: Path, text: str) -> None:
    _wait_for(lambda: path.exists() and text in path.read_text(), timeout=10)


def _wait_for_state(runner: UpdateRunner, state: UpdateState) -> None:
    _wait_for(lambda: runner.progress().state is state, timeout=10)


def _runner(tmp_path: Path, body: str) -> UpdateRunner:
    """A runner whose script is `body`. The last line keeps bash itself running the script
    to its end, so the process stays update.sh."""
    (tmp_path / STAND_IN).write_text(f"{body}\n:\n")
    return UpdateRunner(tmp_path, STAND_IN)


def _python(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


def _write(tmp_path: Path, relative_path: str, text: str) -> None:
    UpdateFiles(tmp_path).write(relative_path, text)


@pytest.fixture
def terminal_update(tmp_path: Path) -> Iterator[subprocess.Popen[bytes]]:
    """An update started from the terminal: update.sh runs and its pid is in the file."""
    script = subprocess.Popen(["/bin/bash", "-c", f"sleep {LONG_S}; :", STAND_IN])
    _write(tmp_path, UpdateFiles.PID, str(script.pid))
    yield script
    script.kill()
    script.wait()


def test_start_writes_running_and_runs_the_script_in_the_project_dir(tmp_path: Path) -> None:
    marker = tmp_path / "cwd"
    runner = _runner(tmp_path, f"pwd > {marker}; sleep 2")

    runner.start()

    assert runner.progress().state is UpdateState.RUNNING
    _wait_for_text(marker, tmp_path.name)


def test_the_pid_in_the_file_is_the_scripts_own(tmp_path: Path) -> None:
    marker = tmp_path / "own-pid"
    runner = _runner(tmp_path, f"echo $$ > {marker}; sleep 2")

    runner.start()

    _wait_for_text(marker, "\n")
    assert (tmp_path / UpdateFiles.PID).read_text() == marker.read_text().strip()


def test_the_script_gets_none_of_the_apps_open_files(tmp_path: Path) -> None:
    """Whatever the app has open must not outlive it in the servers the update starts."""
    marker = tmp_path / "open-fds"
    code = (
        "import os\n"
        "fds = []\n"
        "for fd in range(3, 256):\n"
        "    try:\n"
        "        os.fstat(fd)\n"
        "    except OSError:\n"
        "        continue\n"
        "    fds.append(fd)\n"
        f"open({str(marker)!r}, 'w').write(str(fds))\n"
    )
    runner = _runner(tmp_path, _python(code))
    with (tmp_path / "held-by-the-app").open("w"):
        runner.start()

        _wait_for_text(marker, "]")

    assert marker.read_text() == "[]"


def test_the_script_writes_nothing_to_the_log_through_the_runner(tmp_path: Path) -> None:
    """The script logs on its own; the runner must not log its output a second time."""
    runner = _runner(tmp_path, "echo twice")

    runner.start()

    _wait_for_state(runner, UpdateState.FAILED)
    log = tmp_path / UpdateFiles.LOG
    assert not log.exists() or "twice" not in log.read_text()


def test_the_update_never_waits_for_a_git_password(tmp_path: Path) -> None:
    marker = tmp_path / "env"
    code = (
        "import os, sys\n"
        f"open({str(marker)!r}, 'w').write(os.environ.get('GIT_TERMINAL_PROMPT', '') + ' '"
        " + str(sys.stdin.read() == ''))\n"
    )
    runner = _runner(tmp_path, _python(code))

    runner.start()

    _wait_for_text(marker, "0 True")


def test_failed_state_carries_the_end_of_the_log(tmp_path: Path) -> None:
    _write(tmp_path, UpdateFiles.STATE, "failed\n")
    _write(tmp_path, UpdateFiles.LOG, "\n".join(f"line {n}" for n in range(100)))

    progress = UpdateRunner(tmp_path).progress()

    lines = progress.log_tail.splitlines()
    assert progress.state is UpdateState.FAILED
    assert len(lines) == UpdateFiles.LOG_TAIL_LINES
    assert lines[-1] == "line 99"


def test_start_clears_the_cause_of_the_previous_failure(tmp_path: Path) -> None:
    _write(tmp_path, UpdateFiles.ERROR, "Не получилось запустить новую версию (make up).")
    runner = _runner(tmp_path, "true")

    runner.start()

    _wait_for_state(runner, UpdateState.FAILED)
    assert "make up" not in runner.progress().log_tail


def test_unknown_state_word_counts_as_idle(tmp_path: Path) -> None:
    _write(tmp_path, UpdateFiles.STATE, "garbage")

    assert UpdateRunner(tmp_path).progress().state is UpdateState.IDLE


def test_a_script_that_cannot_run_marks_the_update_failed(tmp_path: Path) -> None:
    runner = UpdateRunner(tmp_path, "scripts/missing.sh")

    runner.start()

    _wait_for_state(runner, UpdateState.FAILED)


def test_a_script_that_dies_without_a_state_ends_failed_with_its_log(tmp_path: Path) -> None:
    runner = _runner(tmp_path, f"mkdir -p .logs; echo boom >> {UpdateFiles.LOG}")

    runner.start()

    _wait_for_state(runner, UpdateState.FAILED)
    assert "boom" in runner.progress().log_tail
    assert (tmp_path / UpdateFiles.STATE).read_text() == "failed"


def test_running_without_a_pid_file_is_failed(tmp_path: Path) -> None:
    _write(tmp_path, UpdateFiles.STATE, "running")

    assert UpdateRunner(tmp_path).progress().state is UpdateState.FAILED


def test_running_with_a_dead_pid_is_failed(tmp_path: Path) -> None:
    dead = subprocess.Popen(["/bin/bash", "-c", "exit 0", STAND_IN])
    dead.wait()
    _write(tmp_path, UpdateFiles.STATE, "running")
    _write(tmp_path, UpdateFiles.PID, str(dead.pid))

    assert UpdateRunner(tmp_path).progress().state is UpdateState.FAILED


def test_a_pid_another_process_got_since_does_not_count_as_the_update(tmp_path: Path) -> None:
    """After a reboot the old pid may belong to anything; the button must not stay blocked."""
    other = subprocess.Popen(["sleep", str(LONG_S)])
    try:
        _write(tmp_path, UpdateFiles.STATE, "running")
        _write(tmp_path, UpdateFiles.PID, str(other.pid))

        assert UpdateRunner(tmp_path).progress().state is UpdateState.FAILED
    finally:
        other.kill()
        other.wait()


def test_running_while_the_script_lives_stays_running(
    tmp_path: Path, terminal_update: subprocess.Popen[bytes],
) -> None:
    _write(tmp_path, UpdateFiles.STATE, "running")

    assert UpdateRunner(tmp_path).progress().state is UpdateState.RUNNING


def test_start_is_refused_while_an_update_from_the_terminal_runs(
    tmp_path: Path, terminal_update: subprocess.Popen[bytes],
) -> None:
    _write(tmp_path, UpdateFiles.STATE, "running")

    with pytest.raises(UpdateAlreadyRunningError):
        _runner(tmp_path, "true").start()


def test_start_is_refused_while_the_update_runs(tmp_path: Path) -> None:
    runner = _runner(tmp_path, "sleep 2")
    runner.start()

    with pytest.raises(UpdateAlreadyRunningError):
        runner.start()


def test_concurrent_starts_spawn_one_process(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    runner = _runner(tmp_path, f"printf x >> {marker}; sleep 2")
    outcomes: list[bool] = []

    def attempt() -> None:
        try:
            runner.start()
            outcomes.append(True)
        except UpdateAlreadyRunningError:
            outcomes.append(False)

    threads = [threading.Thread(target=attempt) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    _wait_for_text(marker, "x")
    time.sleep(0.3)

    assert outcomes.count(True) == 1
    assert marker.read_text() == "x"


def test_a_finished_update_lets_the_next_one_start(tmp_path: Path) -> None:
    marker = tmp_path / "runs"
    runner = _runner(tmp_path, f"printf x >> {marker}; printf done > {UpdateFiles.STATE}")

    runner.start()
    _wait_for_state(runner, UpdateState.DONE)
    runner.start()

    _wait_for_text(marker, "xx")


def test_steps_come_from_the_progress_file_in_order(tmp_path: Path) -> None:
    _write(tmp_path, UpdateFiles.STATE, "done")
    _write(tmp_path, UpdateFiles.PROGRESS, "done\tСкачиваем v1.2.0\ncurrent\tУстанавливаем v1.2.0\n")

    steps = UpdateRunner(tmp_path).progress().steps

    assert steps == [
        UpdateStep(title="Скачиваем v1.2.0", status=UpdateStepStatus.DONE),
        UpdateStep(title="Устанавливаем v1.2.0", status=UpdateStepStatus.CURRENT),
    ]


def test_a_failed_update_keeps_its_steps(tmp_path: Path) -> None:
    _write(tmp_path, UpdateFiles.STATE, "failed")
    _write(tmp_path, UpdateFiles.PROGRESS, "done\tСкачиваем v1.2.0\nfailed\tУстанавливаем v1.2.0\n")

    progress = UpdateRunner(tmp_path).progress()

    assert [step.status for step in progress.steps] == [UpdateStepStatus.DONE, UpdateStepStatus.FAILED]


def test_without_a_progress_file_there_are_no_steps(tmp_path: Path) -> None:
    assert UpdateRunner(tmp_path).progress().steps == []


@pytest.mark.parametrize(
    "garbled",
    [
        "done\tСкачиваем v1.2.0\nhalfway\tУстанавливаем v1.2.0\n",
        "done Скачиваем v1.2.0\n",
        "current\t \n",
    ],
)
def test_a_garbled_progress_file_gives_no_steps(tmp_path: Path, garbled: str) -> None:
    _write(tmp_path, UpdateFiles.STATE, "done")
    _write(tmp_path, UpdateFiles.PROGRESS, garbled)

    assert UpdateRunner(tmp_path).progress().steps == []
