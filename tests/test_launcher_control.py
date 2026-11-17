"""`where-to-go up`, `down` and `status` against a stand-in server that starts processes of its own, as the
real one starts Claude's: real processes, real ports, on every platform the app supports."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psutil
import pytest

from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.control import LaunchError, ServerControl
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.processes import ProcessTree, find_process, protected_pids
from where_to_go.launcher.spec import HOST, ServerSpec

FAKE_SERVER = Path(__file__).parent / "fakes" / "where-to-go"
WAIT_S = 20
LONG_S = 600


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port: int = probe.getsockname()[1]
        return port


def wait_for(condition: Callable[[], bool], timeout: float = WAIT_S) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.05)


def listens(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex((HOST, port)) == 0


class Copy:
    def __init__(self, root: Path) -> None:
        root.mkdir()
        self.paths = ProjectPaths(root)
        self.data = root / "data"
        self.port = free_port()
        self.said: list[str] = []
        config = InstanceConfig(port=self.port, data_dir=self.data, instance="test", menu_bar_icon=False)
        self.control = ServerControl(self.paths, config, say=self.said.append, cli=[sys.executable, str(FAKE_SERVER)])
        self.started: list[subprocess.Popen[bytes]] = []

    def spec(self, port: int | None = None) -> ServerSpec:
        return ServerSpec(port=port or self.port, data_dir=self.data, ui=None, instance="test")

    def family(self, port: int | None = None) -> list[psutil.Process]:
        """The server on the port and everything it started."""
        [server] = self.control.running(port or self.port)
        return [server.process, *server.process.children(recursive=True)]

    def start_by_hand(self, port: int | None = None) -> subprocess.Popen[bytes]:
        """A server started without the launcher and without a record, as `uv run where-to-go` in a terminal
        or the `make up` of an older release started it."""
        port = port or self.port
        process = subprocess.Popen(
            [sys.executable, str(FAKE_SERVER), "--port", str(port), "--data", str(self.data), "--no-record"], cwd=self.paths.root,
        )
        self.started.append(process)
        wait_for(lambda: listens(port))
        return process


@pytest.fixture
def copy(tmp_path: Path) -> Iterator[Copy]:
    result = Copy(tmp_path / "copy")
    yield result
    result.control.down()
    for process in result.started:
        process.kill()
        process.wait()


def is_or_started_by(process: psutil.Process, started: subprocess.Popen[bytes]) -> bool:
    """On Windows a virtual environment's python.exe runs the real interpreter as its child."""
    return process.pid == started.pid or started.pid in {parent.pid for parent in process.parents()}


def gone(processes: list[psutil.Process]) -> bool:
    return all(find_process(process.pid, process.create_time()) is None for process in processes)


def test_up_starts_a_server_that_status_finds(copy: Copy) -> None:
    copy.control.up(copy.spec(), build=False)

    [server] = copy.control.running()
    assert server.spec.port == copy.port
    assert server.spec.data_dir == copy.data.resolve()
    assert copy.control.version_of(server.spec) == "9.9.9"
    assert copy.paths.server_record(copy.port).is_file()


def test_down_stops_the_server_and_everything_it_started(copy: Copy) -> None:
    copy.control.up(copy.spec(), build=False)
    wait_for(lambda: len(copy.family()) >= 3)
    family = copy.family()

    stopped = copy.control.down()

    assert [server.spec.port for server in stopped] == [copy.port]
    wait_for(lambda: gone(family))
    assert not listens(copy.port)
    assert not copy.paths.server_record(copy.port).exists()
    assert copy.control.running() == []


def test_down_with_nothing_running_says_so(copy: Copy) -> None:
    assert copy.control.down() == []
    assert copy.said == ["What To Do is not running."]


def test_up_again_replaces_the_running_server(copy: Copy) -> None:
    copy.control.up(copy.spec(), build=False)
    first = copy.family()

    copy.control.up(copy.spec(), build=False)

    wait_for(lambda: gone(first))
    [server] = copy.control.running()
    assert server.process.pid != first[0].pid
    assert listens(copy.port)


def test_a_port_taken_by_another_program_refuses_the_start_and_names_it(copy: Copy) -> None:
    stranger = subprocess.Popen([sys.executable, "-m", "http.server", str(copy.port), "--bind", HOST], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    copy.started.append(stranger)
    wait_for(lambda: listens(copy.port))

    with pytest.raises(LaunchError, match=f"Port {copy.port} is taken by another program"):
        copy.control.up(copy.spec(), build=False)

    assert stranger.poll() is None


def test_a_server_that_dies_on_start_shows_the_end_of_its_log(copy: Copy) -> None:
    copy.data.mkdir()
    (copy.data / "fail").write_text("", encoding="utf-8")

    with pytest.raises(LaunchError, match="boom on start"):
        copy.control.up(copy.spec(), build=False)


def test_a_record_of_a_dead_server_is_dropped(copy: Copy) -> None:
    copy.control.up(copy.spec(), build=False)
    [server] = copy.control.running()
    server.process.kill()
    server.process.wait(WAIT_S)

    assert copy.control.running() == []
    assert not copy.paths.server_record(copy.port).exists()


def test_a_server_started_by_hand_is_found_and_stopped(copy: Copy) -> None:
    by_hand = copy.start_by_hand()

    [server] = copy.control.running()
    assert is_or_started_by(server.process, by_hand)
    assert server.spec.port == copy.port
    copy.control.down()

    assert by_hand.wait(WAIT_S) is not None


def test_a_server_of_an_older_release_is_found_by_its_pid_file(copy: Copy) -> None:
    other_port = free_port()
    older = copy.start_by_hand(other_port)
    copy.paths.pids.mkdir(exist_ok=True)
    copy.paths.legacy_app_pid.write_text(str(older.pid), encoding="utf-8")

    [server] = copy.control.running()
    assert server.spec.port == other_port
    copy.control.down()

    assert older.wait(WAIT_S) is not None
    assert not copy.paths.legacy_app_pid.exists()
    assert not listens(other_port)


def test_a_server_of_another_copy_on_the_port_is_not_ours(copy: Copy, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    stranger = subprocess.Popen(
        [sys.executable, str(FAKE_SERVER), "--port", str(copy.port), "--data", str(tmp_path / "other-data"), "--no-record"], cwd=other,
    )
    copy.started.append(stranger)
    wait_for(lambda: listens(copy.port))

    assert copy.control.running() == []
    copy.control.down()
    assert stranger.poll() is None


def stranger_on(copy: Copy, port: int) -> subprocess.Popen[bytes]:
    stranger = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", HOST], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    copy.started.append(stranger)
    wait_for(lambda: listens(port))
    return stranger


def control_with(copy: Copy, port: int, *, fixed: bool) -> ServerControl:
    config = InstanceConfig(port=port, data_dir=copy.data, instance="test", menu_bar_icon=False, port_fixed=fixed)
    return ServerControl(copy.paths, config, say=copy.said.append, cli=[sys.executable, str(FAKE_SERVER)])


def test_a_port_another_program_holds_moves_the_copy_to_a_free_one_and_it_stays_there(copy: Copy) -> None:
    stranger_on(copy, copy.port)

    moved = control_with(copy, copy.port, fixed=False).choose_port()

    assert moved != copy.port and not listens(moved)
    assert copy.paths.chosen_port.read_text(encoding="utf-8").strip() == str(moved)
    assert copy.said == [f"Port {copy.port} is taken by another program, so What To Do moves to port {moved} and stays there."]
    assert InstanceConfig.load(copy.paths, environ={}).port == moved


def test_a_free_port_or_the_copys_own_server_keeps_the_port(copy: Copy) -> None:
    assert control_with(copy, copy.port, fixed=False).choose_port() == copy.port
    copy.control.up(copy.spec(), build=False)

    assert control_with(copy, copy.port, fixed=False).choose_port() == copy.port
    assert not copy.paths.chosen_port.exists()


def test_a_port_the_user_set_is_kept_even_when_taken(copy: Copy) -> None:
    stranger_on(copy, copy.port)

    assert control_with(copy, copy.port, fixed=True).choose_port() == copy.port
    assert not copy.paths.chosen_port.exists()


def test_a_port_from_the_environment_or_env_file_is_fixed(copy: Copy) -> None:
    assert InstanceConfig.load(copy.paths, environ={"WHERE_TO_GO_PORT": "18799"}).port_fixed
    copy.paths.env_file.write_text("PORT=18800\n", encoding="utf-8")
    assert InstanceConfig.load(copy.paths, environ={}).port == 18800
    assert InstanceConfig.load(copy.paths, environ={}).port_fixed
    copy.paths.env_file.unlink()
    assert not InstanceConfig.load(copy.paths, environ={}).port_fixed


def test_up_takes_the_port_back_from_the_update_progress_page(copy: Copy) -> None:
    status_server = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({LONG_S})", "update_status_server"])
    copy.started.append(status_server)
    copy.paths.pids.mkdir(exist_ok=True)
    copy.paths.status_server_pid(copy.port).write_text(str(status_server.pid), encoding="utf-8")

    copy.control.up(copy.spec(), build=False)

    assert status_server.wait(WAIT_S) is not None
    assert not copy.paths.status_server_pid(copy.port).exists()


def test_a_process_that_reused_the_progress_pages_pid_is_left_alone(copy: Copy) -> None:
    other = subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({LONG_S})"])
    copy.started.append(other)
    copy.paths.pids.mkdir(exist_ok=True)
    copy.paths.status_server_pid(copy.port).write_text(str(other.pid), encoding="utf-8")

    copy.control.up(copy.spec(), build=False)

    assert other.poll() is None
    assert not copy.paths.status_server_pid(copy.port).exists()


def test_restart_starts_each_server_again_as_it_ran(copy: Copy) -> None:
    second_port = free_port()
    copy.control.up(copy.spec(), build=False)
    copy.control.up(copy.spec(second_port), build=False)
    before = {server.spec.port: server.process.pid for server in copy.control.running()}

    copy.control.restart()

    after = {server.spec.port: server.process.pid for server in copy.control.running()}
    assert set(after) == {copy.port, second_port}
    assert all(after[port] != before[port] for port in after)


def test_a_stop_never_takes_down_whoever_asked_for_it(tmp_path: Path) -> None:
    child_pid = tmp_path / "child.pid"
    code = (
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep({LONG_S})'])\n"
        f"open({str(child_pid)!r}, 'w').write(str(child.pid))\n"
        f"time.sleep({LONG_S})\n"
    )
    parent = subprocess.Popen([sys.executable, "-c", code])
    wait_for(lambda: child_pid.exists() and child_pid.read_text(encoding="utf-8") != "")
    child = psutil.Process(int(child_pid.read_text(encoding="utf-8")))
    try:
        report = ProcessTree(protected={child.pid}).stop(psutil.Process(parent.pid))

        assert report.root_stopped
        assert child.is_running()
    finally:
        child.kill()
        parent.wait(WAIT_S)


def test_the_launcher_protects_itself_and_whoever_started_it() -> None:
    me = psutil.Process()
    assert {me.pid, *(parent.pid for parent in me.parents())} <= protected_pids()
