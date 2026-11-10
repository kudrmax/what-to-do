"""The status server update.sh runs while the app is stopped: it answers the page as the
app would, on the system Python; `make up` stops it before the app takes the port."""

from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

from where_to_go.updating import UpdateFiles, UpdateRunner, UpdateStepStatus

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "update_status_server.py"
MAKEFILE = ROOT / "Makefile"
# The interpreter update.sh runs it with: the copy's .venv is replaced during the update.
SYSTEM_PYTHON = "/usr/bin/python3"
HOST = "127.0.0.1"
WAIT_S = 10
# Outlives any test: only the test or the hook may end it.
DUMMY_S = 600
PROGRESS = "done\tСкачиваем v1.2.0\ncurrent\tУстанавливаем v1.2.0\npending\tЗапускаем новую версию\n"
STATUS_PID_FILE = ".pids/update_status.pid"


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port: int = probe.getsockname()[1]
        return port


class StatusServer:
    def __init__(self, project_dir: Path) -> None:
        self.port = _free_port()
        self.process = subprocess.Popen(
            [SYSTEM_PYTHON, str(SERVER), "--port", str(self.port), "--host", HOST], cwd=project_dir,
        )
        deadline = time.monotonic() + WAIT_S
        while not self.listens():
            assert self.process.poll() is None, "the status server exited"
            assert time.monotonic() < deadline, "the status server never listened"
            time.sleep(0.05)

    def listens(self) -> bool:
        with socket.socket() as probe:
            return probe.connect_ex((HOST, self.port)) == 0

    def get(self, path: str) -> tuple[int, str]:
        try:
            with urllib.request.urlopen(f"http://{HOST}:{self.port}{path}", timeout=WAIT_S) as response:  # noqa: S310
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            return error.code, ""

    def post(self, path: str) -> int:
        request = urllib.request.Request(f"http://{HOST}:{self.port}{path}", data=b"", method="POST")
        try:
            with urllib.request.urlopen(request, timeout=WAIT_S) as response:  # noqa: S310
                return response.status
        except urllib.error.HTTPError as error:
            return error.code

    def stop(self) -> None:
        self.process.kill()
        self.process.wait(timeout=WAIT_S)


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Path]:
    """A copy in the middle of an update: its script runs and wrote its stages."""
    files = UpdateFiles(tmp_path)
    files.write(UpdateFiles.STATE, "running")
    files.write(UpdateFiles.PROGRESS, PROGRESS)
    script = subprocess.Popen(["/bin/bash", "-c", f"sleep {DUMMY_S}; :", "update.sh"])
    files.write(UpdateFiles.PID, str(script.pid))
    yield tmp_path
    script.kill()
    script.wait()


@pytest.fixture
def server(project: Path) -> Iterator[StatusServer]:
    started = StatusServer(project)
    yield started
    started.stop()


def test_state_answers_as_the_app_does(project: Path, server: StatusServer) -> None:
    status, body = server.get("/api/update/state")

    app_answer = UpdateRunner(project).progress()
    assert status == 200
    assert json.loads(body) == app_answer.model_dump(mode="json")
    assert app_answer.steps[1].status is UpdateStepStatus.CURRENT


def test_state_follows_the_progress_file(project: Path, server: StatusServer) -> None:
    (project / UpdateFiles.PROGRESS).write_text("done\tСкачиваем v1.2.0\n")

    _, body = server.get("/api/update/state")

    assert json.loads(body)["steps"] == [{"title": "Скачиваем v1.2.0", "status": "done"}]


def test_garbled_progress_gives_no_steps(project: Path, server: StatusServer) -> None:
    (project / UpdateFiles.PROGRESS).write_text("halfway\tСохраняем копию\n")

    _, body = server.get("/api/update/state")

    assert json.loads(body)["steps"] == []


def test_the_version_and_everything_else_are_unavailable(server: StatusServer) -> None:
    """The page waits for the real server by its version."""
    assert server.get("/api/version")[0] == 503
    assert server.get("/api/updates")[0] == 503
    assert server.post("/api/update") == 503


def _stop_hook(project: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", "--no-print-directory", "-f", str(MAKEFILE), "-C", str(project), "_stop-update-status-server"],
        capture_output=True, text=True, timeout=30, check=False,
    )


def _dummy(project: Path, *argv: str) -> subprocess.Popen[bytes]:
    process = subprocess.Popen(argv)
    UpdateFiles(project).write(STATUS_PID_FILE, str(process.pid))
    return process


def test_make_up_hook_stops_the_registered_status_server(tmp_path: Path) -> None:
    server = _dummy(tmp_path, "python3", "-c", f"import time; time.sleep({DUMMY_S})", "update_status_server")
    try:
        result = _stop_hook(tmp_path)

        assert result.returncode == 0, result.stdout + result.stderr
        assert server.wait(timeout=5) is not None
        assert not (tmp_path / STATUS_PID_FILE).exists()
    finally:
        server.kill()
        server.wait()


def test_make_up_hook_leaves_a_process_that_reused_the_pid_alone(tmp_path: Path) -> None:
    other = _dummy(tmp_path, "sleep", str(DUMMY_S))
    try:
        result = _stop_hook(tmp_path)

        assert result.returncode == 0, result.stdout + result.stderr
        assert other.poll() is None
        assert not (tmp_path / STATUS_PID_FILE).exists()
    finally:
        other.kill()
        other.wait()
