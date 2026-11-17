"""Stands in for `where-to-go`, `uv sync` and the macOS app's build while the updater runs against a test copy.

Every command records itself in $CALLS. Files in $FLAGS switch behaviour on: servers.json is what
`status --json` answers; hold makes `down` wait while it says "hold", hold_up makes `up` wait while it
says "hold"; fail_up makes `up` fail on the version written in it. `up` stops the update's progress page
by its pid file, as the real one does, records in up_saw whether it was still alive and which stage was
current, and fails when something still listens on the port."""

import json
import os
import socket
import sys
import time
from pathlib import Path

import psutil

CALLS = Path(os.environ["CALLS"])
FLAGS = Path(os.environ["FLAGS"])


def record(text: str) -> None:
    with CALLS.open("a", encoding="utf-8") as calls:
        calls.write(text + "\n")


def flag(name: str) -> str:
    path = FLAGS / name
    return path.read_text(encoding="utf-8") if path.exists() else ""


def hold(name: str) -> None:
    while flag(name) == "hold":
        time.sleep(0.05)


def listens(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def up(arguments: list[str]) -> int:
    hold("hold_up")
    version = Path("VERSION").read_text(encoding="utf-8").strip()
    port = int(arguments[arguments.index("--port") + 1])
    record(f"up {version}")
    pid_file = Path(".pids") / f"update_status-{port}.pid"
    seen = "gone"
    if pid_file.exists():
        pid = int(pid_file.read_text(encoding="utf-8"))
        if psutil.pid_exists(pid) and any("update_status_server" in part for part in psutil.Process(pid).cmdline()):
            current = next((line for line in Path(".pids/update.progress").read_text(encoding="utf-8").splitlines() if line.startswith("current")), "")
            seen = f"alive {current}"
            status_server = psutil.Process(pid)
            status_server.terminate()
            try:
                while status_server.is_running() and status_server.status() != psutil.STATUS_ZOMBIE:
                    time.sleep(0.05)
            except psutil.NoSuchProcess:
                pass
        pid_file.unlink()
    with (FLAGS / "up_saw").open("a", encoding="utf-8") as saw:
        saw.write(seen + "\n")
    if listens(port):
        print("port busy")
        return 1
    if flag("fail_up") == version:
        print("broke")
        return 1
    return 0


def main() -> int:
    command, *arguments = sys.argv[1:]
    if command == "status":
        servers = flag("servers.json") or '{"servers": []}'
        print(json.dumps(json.loads(servers)))
        return 0
    if command == "up":
        return up(arguments)
    record(command)
    if command == "sync":
        stdin = "empty" if sys.stdin.read() == "" else "not empty"
        (FLAGS / "sync_environment").write_text(f"GIT_TERMINAL_PROMPT={os.environ.get('GIT_TERMINAL_PROMPT', '')} stdin={stdin}", encoding="utf-8")
    if command == "down":
        hold("hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
