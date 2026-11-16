from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass

import psutil

from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.processes import find_process
from where_to_go.launcher.spec import ServerRecord, ServerSpec


class ServerAlreadyRunningError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveServer:
    record: ServerRecord
    process: psutil.Process


class ServerRecords:
    """The records running servers of a copy keep in `.pids`, one per port. A record whose process is gone
    is removed when read."""

    def __init__(self, paths: ProjectPaths) -> None:
        self._paths = paths

    def register(self, spec: ServerSpec, version: str) -> ServerRecord:
        """Called by a server as it starts. Another live server of this copy on the port refuses the start."""
        existing = self.live(spec.port)
        if existing is not None and existing.record.pid != os.getpid():
            raise ServerAlreadyRunningError(f"This copy already runs a server on port {spec.port} (PID {existing.record.pid}). Stop it first: where-to-go down")
        me = psutil.Process()
        record = ServerRecord(pid=me.pid, create_time=me.create_time(), spec=spec, version=version)
        path = self._paths.server_record(spec.port)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(record.dumps(), encoding="utf-8")
        temporary.replace(path)
        return record

    def unregister(self, record: ServerRecord) -> None:
        path = self._paths.server_record(record.spec.port)
        current = self._read(path)
        if current is not None and current.pid == record.pid:
            path.unlink(missing_ok=True)

    def live(self, port: int) -> LiveServer | None:
        return self._live(self._paths.server_record(port))

    def all_live(self) -> list[LiveServer]:
        return [server for path in self._paths.server_records() if (server := self._live(path)) is not None]

    def _live(self, path: os.PathLike[str]) -> LiveServer | None:
        record = self._read(path)
        if record is None:
            return None
        process = find_process(record.pid, record.create_time)
        if process is None:
            self._forget(path)
            return None
        return LiveServer(record, process)

    @staticmethod
    def _read(path: os.PathLike[str]) -> ServerRecord | None:
        try:
            with open(path, encoding="utf-8") as file:
                return ServerRecord.loads(file.read())
        except (OSError, ValueError, KeyError):
            return None

    @staticmethod
    def _forget(path: os.PathLike[str]) -> None:
        try:
            Path(path).unlink()
        except OSError:
            pass
