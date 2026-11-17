from __future__ import annotations

import os
import socket
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from where_to_go.launcher.spec import HOST

CREATE_TIME_TOLERANCE_S = 0.01


def find_process(pid: int, create_time: float | None = None) -> psutil.Process | None:
    """The live process with this pid; with `create_time`, only if it is the same process, not a later one that got the pid."""
    try:
        process = psutil.Process(pid)
        if create_time is not None and abs(process.create_time() - create_time) > CREATE_TIME_TOLERANCE_S:
            return None
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        return process
    except (psutil.Error, ValueError):
        return None


def command_line(process: psutil.Process) -> list[str]:
    try:
        return process.cmdline()
    except psutil.Error:
        return []


def working_dir(process: psutil.Process) -> Path | None:
    try:
        return Path(process.cwd()).resolve()
    except (psutil.Error, OSError):
        return None


def protected_pids() -> set[int]:
    """This process and those that started it: a stop must never take down whoever asked for it."""
    pids = {os.getpid()}
    try:
        pids.update(parent.pid for parent in psutil.Process().parents())
    except psutil.Error:
        pass
    return pids


@dataclass
class StopReport:
    root_stopped: bool
    leftovers: list[int] = field(default_factory=list)


class ProcessTree:
    """Stops a process and everything it started, at any depth.

    The process goes first and gets time to shut down on its own: the server closes the database and
    stops Claude's calls. Whatever it started and is still running after that is stopped too, so a
    Claude call never outlives the app and keeps reading after it was closed."""

    GRACE_S = 15.0
    LEFTOVER_GRACE_S = 5.0

    def __init__(self, protected: Iterable[int] = ()) -> None:
        self._protected = set(protected)

    POLL_S = 0.05

    def stop(self, root: psutil.Process) -> StopReport:
        descendants = self._descendants(root)
        self._terminate([root])
        alive = self._wait_gone([root], self.GRACE_S)
        if alive:
            self._kill(alive)
            self._wait_gone(alive, self.LEFTOVER_GRACE_S)
        leftovers = self._still_running(descendants)
        for process in list(leftovers):
            leftovers.extend(child for child in self._descendants(process) if child not in leftovers)
        self._terminate(leftovers)
        stubborn = self._wait_gone(leftovers, self.LEFTOVER_GRACE_S)
        self._kill(stubborn)
        self._wait_gone(stubborn, self.LEFTOVER_GRACE_S)
        return StopReport(root_stopped=not self._still_running([root]), leftovers=[process.pid for process in leftovers])

    def _wait_gone(self, processes: list[psutil.Process], timeout_s: float) -> list[psutil.Process]:
        """A stopped process whose parent has not collected it yet counts as gone: psutil's own wait would
        wait for that parent."""
        deadline = time.monotonic() + timeout_s
        alive = self._still_running(processes)
        while alive and time.monotonic() < deadline:
            time.sleep(self.POLL_S)
            alive = self._still_running(alive)
        return alive

    def _descendants(self, process: psutil.Process) -> list[psutil.Process]:
        """A protected process keeps what it started: on Windows a venv's python.exe is only a launcher, and
        the interpreter doing the work is its child."""
        try:
            children = process.children(recursive=True)
        except psutil.Error:
            return []
        inside = [child for child in children if child.pid in self._protected]
        spared = self._protected | self._started_by(inside)
        return [child for child in children if child.pid not in spared]

    @staticmethod
    def _started_by(processes: list[psutil.Process]) -> set[int]:
        pids: set[int] = set()
        for process in processes:
            try:
                pids.update(child.pid for child in process.children(recursive=True))
            except psutil.Error:
                continue
        return pids

    @staticmethod
    def _still_running(processes: list[psutil.Process]) -> list[psutil.Process]:
        running = []
        for process in processes:
            try:
                if process.is_running() and process.status() != psutil.STATUS_ZOMBIE:
                    running.append(process)
            except psutil.Error:
                continue
        return running

    def _terminate(self, processes: list[psutil.Process]) -> None:
        for process in processes:
            if process.pid in self._protected:
                continue
            try:
                process.terminate()
            except psutil.Error:
                continue

    def _kill(self, processes: list[psutil.Process]) -> None:
        for process in processes:
            if process.pid in self._protected:
                continue
            try:
                process.kill()
            except psutil.Error:
                continue


class Ports:
    """Who listens on a local TCP port."""

    NEARBY = 20

    @staticmethod
    def is_taken(port: int, host: str = HOST) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(1)
            return probe.connect_ex((host, port)) == 0

    @classmethod
    def free_near(cls, port: int, host: str = HOST) -> int:
        """The first free port after this one, so the address stays recognisable; any free port if all are taken."""
        for candidate in range(port + 1, min(port + cls.NEARBY, 65535) + 1):
            if not cls.is_taken(candidate, host) and cls._can_bind(candidate, host):
                return candidate
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            return int(probe.getsockname()[1])

    @staticmethod
    def _can_bind(port: int, host: str) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError:
                return False
            return True

    @classmethod
    def listeners(cls, port: int) -> list[psutil.Process]:
        """The processes listening on the port that this user may see; empty when none is visible."""
        try:
            pids = {
                connection.pid
                for connection in psutil.net_connections(kind="tcp")
                if connection.status == psutil.CONN_LISTEN and connection.laddr and connection.laddr.port == port and connection.pid
            }
        except psutil.AccessDenied:
            pids = cls._listener_pids_one_by_one(port)
        return [process for pid in sorted(pids) if (process := find_process(pid)) is not None]

    @staticmethod
    def _listener_pids_one_by_one(port: int) -> set[int]:
        """macOS lets only root list every socket at once; a user may still ask each of their own processes."""
        pids = set()
        for process in psutil.process_iter():
            try:
                connections = process.net_connections(kind="tcp")
            except psutil.Error:
                continue
            if any(c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port == port for c in connections):
                pids.add(process.pid)
        return pids

    @classmethod
    def listening_ports(cls, process: psutil.Process) -> list[int]:
        """The ports the process or what it started listens on: on Windows a virtual environment's python.exe
        starts the real interpreter as its child."""
        try:
            family = [process, *process.children(recursive=True)]
        except psutil.Error:
            return []
        return sorted({port for member in family for port in cls._own_listening_ports(member)})

    @staticmethod
    def _own_listening_ports(process: psutil.Process) -> set[int]:
        try:
            return {c.laddr.port for c in process.net_connections(kind="tcp") if c.status == psutil.CONN_LISTEN and c.laddr}
        except psutil.Error:
            return set()
