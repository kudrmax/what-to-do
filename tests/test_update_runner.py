"""The app's update runner on its own, with stand-in updaters: how it starts one and how it tells the
update's state from the files and the process."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from where_to_go.updating import (
    UpdateAlreadyRunningError,
    UpdateFiles,
    UpdateProcess,
    UpdateRunner,
    UpdateState,
    UpdateStep,
    UpdateStepStatus,
)

# The stand-in's mark: the runner knows a running update by it.
STAND_IN = "stand-in-update"
# Outlives any test: only the test may end it.
LONG_S = 600
WAIT_S = 10

# Starts `body` as a process of its own, writes its pid as the real background start does, and returns.
LAUNCHER = """
import subprocess, sys
from where_to_go.launcher.update_journal import UpdateJournal
process = subprocess.Popen(
    [sys.executable, "-c", sys.argv[1], "{mark}"],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=sys.platform != "win32",
)
UpdateJournal(__import__("pathlib").Path.cwd()).write_pid(process.pid)
""".format(mark=STAND_IN)


def is_stand_in(cmdline: list[str]) -> bool:
    return STAND_IN in cmdline


def wait_for(condition: Callable[[], bool], timeout: float = WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def runner(tmp_path: Path, body: str) -> UpdateRunner:
    """A runner whose updater runs the Python `body`."""
    return UpdateRunner(tmp_path, command=[sys.executable, "-c", LAUNCHER, body], is_update=is_stand_in)


def write(tmp_path: Path, relative_path: str, text: str) -> None:
    UpdateFiles(tmp_path).write(relative_path, text)


def wait_for_text(path: Path, text: str) -> None:
    wait_for(lambda: path.exists() and text in path.read_text())


def wait_for_state(update: UpdateRunner, state: UpdateState) -> None:
    wait_for(lambda: update.progress().state is state)


def sleeping(seconds: float = LONG_S) -> str:
    return f"import time; time.sleep({seconds})"


@pytest.fixture
def terminal_update(tmp_path: Path) -> Iterator[subprocess.Popen[bytes]]:
    """An update started from the terminal: it runs and its pid is in the file."""
    process = subprocess.Popen([sys.executable, "-c", sleeping(), STAND_IN])
    write(tmp_path, UpdateFiles.PID, str(process.pid))
    yield process
    process.kill()
    process.wait()


def test_start_writes_running_and_runs_the_updater_in_the_project_dir(tmp_path: Path) -> None:
    marker = tmp_path / "cwd"
    update = runner(tmp_path, f"import os, time; open({str(marker)!r}, 'w').write(os.getcwd()); time.sleep(2)")

    update.start()

    assert update.progress().state is UpdateState.RUNNING
    wait_for_text(marker, tmp_path.name)


def test_the_updater_gets_none_of_the_apps_open_files(tmp_path: Path) -> None:
    """Whatever the app has open must not outlive it in the servers the update starts."""
    marker = tmp_path / "open-fds"
    body = (
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
    update = runner(tmp_path, body)
    with (tmp_path / "held-by-the-app").open("w"):
        update.start()

        wait_for_text(marker, "]")

    assert marker.read_text() == "[]"


def test_the_update_never_waits_for_a_git_password(tmp_path: Path) -> None:
    marker = tmp_path / "env"
    body = f"import os, sys; open({str(marker)!r}, 'w').write(os.environ.get('GIT_TERMINAL_PROMPT', '') + ' ' + str(sys.stdin is None or sys.stdin.read() == ''))"
    runner(tmp_path, body).start()

    wait_for_text(marker, "0 True")


def test_failed_state_carries_the_end_of_the_log(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.STATE, "failed\n")
    write(tmp_path, UpdateFiles.LOG, "\n".join(f"line {n}" for n in range(100)))

    progress = UpdateRunner(tmp_path).progress()

    lines = progress.log_tail.splitlines()
    assert progress.state is UpdateState.FAILED
    assert len(lines) == UpdateFiles.LOG_TAIL_LINES
    assert lines[-1] == "line 99"


def test_the_failure_shows_only_the_last_run_of_either_updater(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.STATE, "failed")
    write(tmp_path, UpdateFiles.LOG, "=== make update 2026\nold\n=== update 2026\nnew \x1b[31mERR\x1b[0m\n")

    assert UpdateRunner(tmp_path).progress().log_tail == "=== update 2026\nnew ERR"


def test_start_clears_the_cause_of_the_previous_failure(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.ERROR, "Couldn't start the new version.")
    update = runner(tmp_path, "pass")

    update.start()

    wait_for_state(update, UpdateState.FAILED)
    assert "Couldn't start" not in update.progress().log_tail


def test_unknown_state_word_counts_as_idle(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.STATE, "garbage")

    assert UpdateRunner(tmp_path).progress().state is UpdateState.IDLE


def test_an_updater_that_cannot_start_marks_the_update_failed_with_why(tmp_path: Path) -> None:
    update = UpdateRunner(tmp_path, command=[sys.executable, "-c", "import sys; print('Another update is already running', file=sys.stderr); sys.exit(1)"])

    update.start()

    progress = update.progress()
    assert progress.state is UpdateState.FAILED
    assert "Another update is already running" in progress.log_tail


def test_a_missing_updater_marks_the_update_failed(tmp_path: Path) -> None:
    update = UpdateRunner(tmp_path, command=[str(tmp_path / "no-such-program")])

    update.start()

    assert update.progress().state is UpdateState.FAILED


def test_an_updater_that_dies_without_a_state_ends_failed_with_its_log(tmp_path: Path) -> None:
    update = runner(tmp_path, f"import os; os.makedirs('.logs', exist_ok=True); open({UpdateFiles.LOG!r}, 'a').write('boom')")

    update.start()

    wait_for_state(update, UpdateState.FAILED)
    assert "boom" in update.progress().log_tail
    assert (tmp_path / UpdateFiles.STATE).read_text() == "failed"


def test_running_without_a_pid_file_is_failed(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.STATE, "running")

    assert UpdateRunner(tmp_path).progress().state is UpdateState.FAILED


def test_running_with_a_dead_pid_is_failed(tmp_path: Path) -> None:
    dead = subprocess.Popen([sys.executable, "-c", "pass", STAND_IN])
    dead.wait()
    write(tmp_path, UpdateFiles.STATE, "running")
    write(tmp_path, UpdateFiles.PID, str(dead.pid))

    assert UpdateRunner(tmp_path, is_update=is_stand_in).progress().state is UpdateState.FAILED


def test_a_pid_another_process_got_since_does_not_count_as_the_update(tmp_path: Path) -> None:
    """After a reboot the old pid may belong to anything; the button must not stay blocked."""
    other = subprocess.Popen([sys.executable, "-c", sleeping()])
    try:
        write(tmp_path, UpdateFiles.STATE, "running")
        write(tmp_path, UpdateFiles.PID, str(other.pid))

        assert UpdateRunner(tmp_path).progress().state is UpdateState.FAILED
    finally:
        other.kill()
        other.wait()


def test_running_while_the_updater_lives_stays_running(tmp_path: Path, terminal_update: subprocess.Popen[bytes]) -> None:
    write(tmp_path, UpdateFiles.STATE, "running")

    assert UpdateRunner(tmp_path, is_update=is_stand_in).progress().state is UpdateState.RUNNING


def test_start_is_refused_while_an_update_from_the_terminal_runs(tmp_path: Path, terminal_update: subprocess.Popen[bytes]) -> None:
    write(tmp_path, UpdateFiles.STATE, "running")

    with pytest.raises(UpdateAlreadyRunningError):
        runner(tmp_path, "pass").start()


def test_start_is_refused_while_the_update_runs(tmp_path: Path) -> None:
    update = runner(tmp_path, sleeping(5))
    update.start()

    with pytest.raises(UpdateAlreadyRunningError):
        update.start()


def test_concurrent_starts_spawn_one_process(tmp_path: Path) -> None:
    marker = tmp_path / "spawned"
    update = runner(tmp_path, f"import time; open({str(marker)!r}, 'a').write('x'); time.sleep(5)")
    outcomes: list[bool] = []

    def attempt() -> None:
        try:
            update.start()
            outcomes.append(True)
        except UpdateAlreadyRunningError:
            outcomes.append(False)

    threads = [threading.Thread(target=attempt) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wait_for_text(marker, "x")
    time.sleep(0.3)

    assert outcomes.count(True) == 1
    assert marker.read_text() == "x"


def test_a_finished_update_lets_the_next_one_start(tmp_path: Path) -> None:
    marker = tmp_path / "runs"
    update = runner(tmp_path, f"open({str(marker)!r}, 'a').write('x'); open({UpdateFiles.STATE!r}, 'w').write('done')")

    update.start()
    wait_for_state(update, UpdateState.DONE)
    update.start()

    wait_for_text(marker, "xx")


@pytest.mark.parametrize(
    ("cmdline", "is_update"),
    [
        (["/usr/bin/python3", "-m", "where_to_go", "update", "--detached-child"], True),
        (["C:\\wtd\\.venv\\Scripts\\python.exe", "-m", "where_to_go", "update", "--detached-child"], True),
        (["/wtd/.venv/bin/python3", "/wtd/.venv/bin/where-to-go", "update"], True),
        (["/bin/bash", "scripts/update.sh"], True),
        (["/wtd/.venv/bin/python3", "/wtd/.venv/bin/where-to-go", "up"], False),
        (["/wtd/.venv/bin/python3", "-m", "where_to_go", "serve", "--port", "18765"], False),
        (["sleep", "600"], False),
    ],
)
def test_the_update_process_is_known_by_its_command_line(cmdline: list[str], is_update: bool) -> None:
    """Also the shell updater of older releases, which runs the update to this release."""
    assert UpdateProcess.matches(cmdline) is is_update


def test_steps_come_from_the_progress_file_in_order(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.STATE, "done")
    write(tmp_path, UpdateFiles.PROGRESS, "done\tСкачиваем v1.2.0\ncurrent\tУстанавливаем v1.2.0\n")

    steps = UpdateRunner(tmp_path).progress().steps

    assert steps == [
        UpdateStep(title="Скачиваем v1.2.0", status=UpdateStepStatus.DONE),
        UpdateStep(title="Устанавливаем v1.2.0", status=UpdateStepStatus.CURRENT),
    ]


def test_a_failed_update_keeps_its_steps(tmp_path: Path) -> None:
    write(tmp_path, UpdateFiles.STATE, "failed")
    write(tmp_path, UpdateFiles.PROGRESS, "done\tСкачиваем v1.2.0\nfailed\tУстанавливаем v1.2.0\n")

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
    write(tmp_path, UpdateFiles.STATE, "done")
    write(tmp_path, UpdateFiles.PROGRESS, garbled)

    assert UpdateRunner(tmp_path).progress().steps == []
