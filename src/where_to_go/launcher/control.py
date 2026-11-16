from __future__ import annotations

import json
import subprocess
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil
from filelock import FileLock, Timeout

from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.frontend import BuildError, FrontendBuild
from where_to_go.launcher.paths import ProjectPaths, python_command
from where_to_go.launcher.processes import Ports, ProcessTree, command_line, find_process, protected_pids, working_dir
from where_to_go.launcher.records import ServerRecords
from where_to_go.launcher.spawning import child_environment, detached
from where_to_go.launcher.spec import LegacyCommandLine, ServerSpec
from where_to_go.launcher.tools import ToolMissingError, Tools

STATUS_SERVER_MARKER = "update_status_server"


class LaunchError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunningServer:
    process: psutil.Process
    spec: ServerSpec
    version: str = ""


class ServerControl:
    """Starts, stops and finds the servers of one copy of the app.

    A server writes a record of itself in the copy's `.pids` while it runs. Servers that wrote none, those
    of releases before 1.16 and those started by hand, are found by the port they listen on, the folder
    they run in and their command line. Starts and stops of a copy run one at a time."""

    START_TIMEOUT_S = 120.0
    LOCK_TIMEOUT_S = 600.0
    POLL_S = 0.25
    PORT_RELEASE_TIMEOUT_S = 10.0
    LOG_TAIL_LINES = 30

    def __init__(
        self,
        paths: ProjectPaths,
        config: InstanceConfig,
        say: Callable[[str], None] = print,
        tools: Tools | None = None,
        cli: list[str] | None = None,
    ) -> None:
        self._paths = paths
        self._config = config
        self._say = say
        self._tools = tools or Tools()
        self._cli = cli or python_command()
        self._records = ServerRecords(paths)

    def default_spec(self) -> ServerSpec:
        return ServerSpec(port=self._config.port, data_dir=self._config.data_dir, ui=self._paths.dist, instance=self._config.instance)

    def running(self, port: int | None = None) -> list[RunningServer]:
        found = {server.record.pid: RunningServer(server.process, server.record.spec, server.record.version) for server in self._records.all_live()}
        for server in self._unrecorded(port if port is not None else self._config.port):
            found.setdefault(server.process.pid, server)
        return [server for server in found.values() if port is None or server.spec.port == port]

    def up(self, spec: ServerSpec, build: bool = True) -> None:
        with self._exclusive():
            self._prepare_interface(spec, build)
            self._stop(self.running(spec.port), say_when_none=False)
            self._stop_status_servers(spec.port)
            self._require_free(spec.port)
            process = self._spawn(spec)
            self._wait_started(spec, process)

    def build(self) -> bool:
        return FrontendBuild(self._paths, self._tools, self._say).ensure()

    def down(self, port: int | None = None) -> list[RunningServer]:
        with self._exclusive():
            servers = self.running(port)
            self._stop(servers, say_when_none=True)
            return servers

    def restart(self) -> list[ServerSpec]:
        specs = [server.spec for server in self.running()] or [self.default_spec()]
        for spec in specs:
            self.up(spec)
        return specs

    def version_of(self, spec: ServerSpec) -> str | None:
        try:
            with urllib.request.urlopen(spec.version_url, timeout=2) as response:  # noqa: S310 — a local address
                answer = json.loads(response.read())
        except (OSError, ValueError, urllib.error.URLError):
            return None
        return answer.get("version") if isinstance(answer, dict) else None

    def _unrecorded(self, port: int) -> list[RunningServer]:
        candidates = Ports.listeners(port)
        legacy = self._legacy_pid()
        if legacy is not None and legacy not in candidates:
            candidates.append(legacy)
        servers = []
        for process in candidates:
            cmdline = command_line(process)
            if not LegacyCommandLine.is_server(cmdline) or not self._belongs_here(process, cmdline):
                continue
            ports = Ports.listening_ports(process)
            listening = port if port in ports or not ports else ports[0]
            cwd = working_dir(process) or self._paths.root
            spec = LegacyCommandLine.spec(cmdline, cwd, listening, InstanceConfig.default_data_dir(), self._config.instance)
            servers.append(RunningServer(process, spec))
        return servers

    def _legacy_pid(self) -> psutil.Process | None:
        try:
            pid = int(self._paths.legacy_app_pid.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None
        process = find_process(pid)
        if process is None:
            self._paths.legacy_app_pid.unlink(missing_ok=True)
        return process

    def _belongs_here(self, process: psutil.Process, cmdline: list[str]) -> bool:
        """Another copy may run on the same port; only this copy's servers are this copy's to stop."""
        root = self._paths.root.resolve()
        if working_dir(process) == root:
            return True
        return any(part == str(root) or part.startswith(str(root) + os.sep) for part in cmdline)

    def _stop(self, servers: list[RunningServer], say_when_none: bool) -> None:
        if not servers and say_when_none:
            self._say("What To Do is not running.")
        tree = ProcessTree(protected=protected_pids())
        for server in servers:
            report = tree.stop(server.process)
            self._say(f"Stopped the server on port {server.spec.port} (PID {server.process.pid}).")
            if report.leftovers:
                self._say(f"Stopped {len(report.leftovers)} process(es) it had started: PID {', '.join(map(str, report.leftovers))}.")
            self._paths.server_record(server.spec.port).unlink(missing_ok=True)
            if not report.root_stopped:
                raise LaunchError(f"The server (PID {server.process.pid}) did not stop.")
            self._wait_port_released(server.spec.port)
        self._legacy_pid()

    def _wait_port_released(self, port: int) -> None:
        deadline = time.monotonic() + self.PORT_RELEASE_TIMEOUT_S
        while Ports.is_taken(port) and time.monotonic() < deadline:
            time.sleep(self.POLL_S)

    def _stop_status_servers(self, port: int) -> None:
        """The update's progress page holds the port while the app is down; it gives the port back here."""
        tree = ProcessTree(protected=protected_pids())
        for pid_file in (self._paths.status_server_pid(port), self._paths.legacy_status_pid):
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            process = find_process(pid)
            if process is not None and any(STATUS_SERVER_MARKER in part for part in command_line(process)):
                tree.stop(process)
            pid_file.unlink(missing_ok=True)

    def _require_free(self, port: int) -> None:
        if not Ports.is_taken(port):
            return
        holders = Ports.listeners(port)
        if holders:
            holder = holders[0]
            where = working_dir(holder)
            raise LaunchError(
                f"Port {port} is taken by another program (PID {holder.pid}{f', running in {where}' if where else ''}):\n"
                f"  {' '.join(command_line(holder))[:160]}\n"
                "Stop it, or start What To Do on another port: where-to-go up --port <number>"
            )
        raise LaunchError(f"Port {port} is taken by another program. Start What To Do on another port: where-to-go up --port <number>")

    def _prepare_interface(self, spec: ServerSpec, build: bool) -> None:
        if spec.ui is None:
            return
        if build and spec.ui.resolve() == self._paths.dist.resolve():
            try:
                self.build()
            except (BuildError, ToolMissingError) as error:
                raise LaunchError(str(error)) from error
        if not (spec.ui / "index.html").is_file():
            raise LaunchError(f"There is no built interface in {spec.ui}. Build it with: where-to-go build")

    def _spawn(self, spec: ServerSpec) -> subprocess.Popen[bytes]:
        self._paths.logs.mkdir(parents=True, exist_ok=True)
        with self._paths.app_log.open("ab") as log:
            log.write(f"=== start {time.strftime('%Y-%m-%dT%H:%M:%S')} on port {spec.port} ===\n".encode())
            log.flush()
            return subprocess.Popen(
                [*self._cli, "serve", *spec.arguments()],
                cwd=self._paths.root,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=child_environment(),
                **detached(),
            )

    def _wait_started(self, spec: ServerSpec, process: subprocess.Popen[bytes]) -> None:
        log_start = self._log_size()
        deadline = time.monotonic() + self.START_TIMEOUT_S
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise LaunchError(f"The app exited on start. The end of {self._paths.app_log}:\n{self._log_tail(log_start)}")
            server = self._records.live(spec.port)
            if server is not None and self.version_of(spec) is not None:
                return
            time.sleep(self.POLL_S)
        raise LaunchError(f"The app (PID {process.pid}) did not open port {spec.port} in time, see {self._paths.app_log}")

    def _log_size(self) -> int:
        try:
            return self._paths.app_log.stat().st_size
        except OSError:
            return 0

    def _log_tail(self, since: int) -> str:
        try:
            with self._paths.app_log.open("rb") as log:
                log.seek(max(0, since - 4096))
                text = log.read().decode("utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-self.LOG_TAIL_LINES:])

    def _exclusive(self) -> _CopyLock:
        return _CopyLock(self._paths.launcher_lock, self._say, self.LOCK_TIMEOUT_S)


class _CopyLock:
    """Starts and stops of one copy run one at a time: the macOS app starts the server on its own."""

    def __init__(self, path: Path, say: Callable[[str], None], timeout_s: float) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(path)
        self._say = say
        self._timeout_s = timeout_s

    def __enter__(self) -> None:
        try:
            self._lock.acquire(timeout=0)
        except Timeout:
            self._say("Waiting for another start or stop of this copy to finish...")
            try:
                self._lock.acquire(timeout=self._timeout_s)
            except Timeout:
                raise LaunchError("Another start or stop of this copy is still running. Try again in a minute.") from None

    def __exit__(self, *_: object) -> None:
        self._lock.release()
