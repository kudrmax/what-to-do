"""Installs nothing and leaves nothing behind: starts the app the way a user does, checks that it answers,
stops it, checks that nothing of it is left running, and uninstalls it. CI runs it on macOS, Linux and
Windows; it runs the same on a developer's computer:

    uv run python scripts/smoke_test.py

By default the app keeps its data in a new temporary folder and runs on a free port. With
`--default-data` it uses the platform's own data folder, as a fresh install does; that folder must not
exist yet, so real data is never touched.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
START_TIMEOUT_S = 180
STOP_TIMEOUT_S = 30
NOT_RUNNING_EXIT = 3


class SmokeTestError(AssertionError):
    pass


class SmokeTest:
    def __init__(self, port: int, data_dir: Path | None) -> None:
        self._port = port
        self._data_dir = data_dir
        self._environ = {**os.environ, "WHERE_TO_GO_PORT": str(port), "PYTHONUTF8": "1"}
        if data_dir is not None:
            self._environ["WHERE_TO_GO_DATA_DIR"] = str(data_dir)
        else:
            self._environ.pop("WHERE_TO_GO_DATA_DIR", None)

    def run(self) -> None:
        version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
        data_dir = self._expected_data_dir()
        self._step(f"data folder {data_dir}, port {self._port}")
        if data_dir.exists() and self._data_dir is None:
            raise SmokeTestError(f"{data_dir} already exists: the smoke test never touches existing data")

        started = self._cli("up")
        self._expect(f"→ http://{HOST}:{self._port}" in started.stdout, "up printed the address", started)
        self._expect(self._get_json("/api/version") == {"version": version}, f"the app answers its version {version}")
        page = self._get("/")
        self._expect(page.startswith(b"<!doctype html>") or b"<div id=\"root\">" in page, "the page loads")
        self._expect(self._get_json("/api/claude/sign-in")["state"] in ("signed_in", "signed_out", "unknown"), "the sign-in check answers")

        status = json.loads(self._cli("status", "--json").stdout)
        [server] = status["servers"]
        self._expect(server["port"] == self._port and Path(server["data_dir"]) == data_dir, "status names the port and the data folder")
        self._expect(data_dir.is_dir(), "the data folder was created")
        family = self._family(server["pid"])
        self._step(f"server PID {server['pid']} with {len(family) - 1} process(es) it started")

        self._cli("down")
        self._expect(self._all_gone(family), "down stopped the server and everything it started")
        self._expect(not self._listens(), f"port {self._port} is free")
        self._expect(not self._leftovers(), "no process of the app is left")
        stopped = self._cli("status", check=False)
        self._expect(stopped.returncode == NOT_RUNNING_EXIT, "status says it is not running", stopped)

        self._cli("up")
        family = self._family(json.loads(self._cli("status", "--json").stdout)["servers"][0]["pid"])
        removed = self._cli("uninstall", "--yes")
        self._expect("Last step: delete the folder" in removed.stdout, "uninstall names the last step", removed)
        self._expect(self._all_gone(family), "uninstall stopped the app")
        self._expect(not self._listens(), f"port {self._port} is free after uninstall")
        self._expect(not data_dir.exists(), "uninstall removed the data folder")
        self._step("PASSED")

    def clean_up(self) -> None:
        self._cli("down", "--port", str(self._port), check=False)

    def _expected_data_dir(self) -> Path:
        if self._data_dir is not None:
            return self._data_dir.resolve()
        status = json.loads(self._cli("status", "--json", check=False).stdout)
        return Path(status["config"]["data_dir"])

    def _cli(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-m", "where_to_go", *arguments]
        self._step("$ where-to-go " + " ".join(arguments))
        completed = subprocess.run(
            command, cwd=ROOT, env=self._environ, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=START_TIMEOUT_S,
        )
        for line in (completed.stdout + completed.stderr).splitlines():
            print(f"    {line}", flush=True)
        if check and completed.returncode != 0:
            raise SmokeTestError(f"where-to-go {' '.join(arguments)} exited with {completed.returncode}")
        return completed

    def _get(self, path: str) -> bytes:
        with urllib.request.urlopen(f"http://{HOST}:{self._port}{path}", timeout=30) as response:  # noqa: S310 — a local address
            return response.read()

    def _get_json(self, path: str) -> dict[str, object]:
        return json.loads(self._get(path))

    def _listens(self) -> bool:
        with socket.socket() as probe:
            return probe.connect_ex((HOST, self._port)) == 0

    @staticmethod
    def _family(pid: int) -> list[psutil.Process]:
        """The server, what it started and, on Windows, the virtual environment's python.exe that started it."""
        server = psutil.Process(pid)
        launcher = [parent for parent in server.parents()[:1] if "serve" in SmokeTest._command_line(parent)]
        return [server, *server.children(recursive=True), *launcher]

    @staticmethod
    def _command_line(process: psutil.Process) -> list[str]:
        try:
            return process.cmdline()
        except psutil.Error:
            return []

    def _all_gone(self, family: list[psutil.Process]) -> bool:
        deadline = time.monotonic() + STOP_TIMEOUT_S
        while time.monotonic() < deadline:
            alive = [process for process in family if self._alive(process)]
            if not alive:
                return True
            time.sleep(0.2)
        print(f"    still running: {[process.pid for process in alive]}", flush=True)
        return False

    def _leftovers(self) -> list[int]:
        """Any process still serving this port, whoever started it."""
        found = []
        for process in psutil.process_iter():
            cmdline = self._command_line(process)
            if "serve" in cmdline and "--port" in cmdline and str(self._port) in cmdline:
                found.append(process.pid)
        if found:
            print(f"    left running: {found}", flush=True)
        return found

    @staticmethod
    def _alive(process: psutil.Process) -> bool:
        try:
            return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
        except psutil.Error:
            return False

    @staticmethod
    def _expect(condition: bool, what: str, completed: subprocess.CompletedProcess[str] | None = None) -> None:
        if not condition:
            details = f"\n{completed.stdout}\n{completed.stderr}" if completed is not None else ""
            raise SmokeTestError(f"FAILED: {what}{details}")
        print(f"ok  {what}", flush=True)

    @staticmethod
    def _step(text: str) -> None:
        print(f"--  {text}", flush=True)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        port: int = probe.getsockname()[1]
        return port


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=0, help="default: a free port")
    parser.add_argument("--default-data", action="store_true", help="use the platform's data folder, which must not exist yet")
    arguments = parser.parse_args()
    port = arguments.port or free_port()
    data_dir = None if arguments.default_data else Path(tempfile.mkdtemp(prefix="where-to-go-smoke-")) / "data"
    smoke = SmokeTest(port, data_dir)
    try:
        smoke.run()
    except SmokeTestError as error:
        print(error, file=sys.stderr, flush=True)
        log = ROOT / ".logs" / "app.log"
        if log.exists():
            print("--- the end of .logs/app.log ---", file=sys.stderr)
            print("\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]), file=sys.stderr)
        smoke.clean_up()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
