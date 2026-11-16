"""Moves a copy to the latest release the way a person would by hand: fetch the tags, stop the app, check
out the newest release, install its packages, build its interface, start the app again as it ran.

The Update button and `where-to-go update` run this. It stops and restarts the servers of the copy and
reinstalls the packages under itself, so it imports only the standard library and pure-Python packages."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from filelock import FileLock, Timeout

from where_to_go.launcher.config import InstanceConfig
from where_to_go.launcher.macos_apps import MacApps
from where_to_go.launcher.paths import ProjectPaths, python_command
from where_to_go.launcher.spawning import child_environment, detached
from where_to_go.launcher.spec import HOST, ServerSpec
from where_to_go.launcher.tools import ToolMissingError, Tools
from where_to_go.launcher.update_journal import StepWord, UpdateJournal, UpdateWord

CHECK = "Checking for a new version"
INSTALL = "Installing the new version"
START = "Starting the new version"
DETACHED_CHILD = "--detached-child"
# The update runs unattended: a git asking for a password would hang it.
NON_INTERACTIVE = {"GIT_TERMINAL_PROMPT": "0"}


class UpdateFailedError(Exception):
    """Says in a sentence what broke; the log has the details."""


class UpdateLog:
    """Everything the update prints goes to the copy's update log, and to the terminal when run from one."""

    def __init__(self, path: Path, echo: TextIO | None) -> None:
        self._path = path
        self._echo = echo

    def start(self) -> None:
        self.say(f"=== update {datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')} ===")

    def say(self, text: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as log:
            log.write(text + "\n")
        if self._echo is not None:
            print(text, file=self._echo, flush=True)

    def run(self, command: Sequence[str | os.PathLike[str]], cwd: Path, env: dict[str, str] | None = None) -> int:
        try:
            process = subprocess.Popen(
                [str(part) for part in command],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env or child_environment(**NON_INTERACTIVE),
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as error:
            self.say(f"Couldn't run {command[0]}: {error}")
            return 127
        assert process.stdout is not None
        for line in process.stdout:
            self.say(line.rstrip("\n"))
        return process.wait()

    def output(self, command: Sequence[str], cwd: Path) -> str | None:
        completed = subprocess.run(
            command, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=child_environment(**NON_INTERACTIVE), check=False,
        )
        if completed.returncode != 0:
            if completed.stderr.strip():
                self.say(completed.stderr.strip())
            return None
        return completed.stdout


class Stages:
    """The stages the user sees, in order."""

    def __init__(self, journal: UpdateJournal) -> None:
        self._journal = journal
        self._steps: list[tuple[StepWord, str]] = []

    def begin(self, *titles: str) -> None:
        self._steps = [(StepWord.CURRENT if index == 0 else StepWord.PENDING, title) for index, title in enumerate(titles)]
        self._save()

    def rename(self, index: int, title: str) -> None:
        self._steps[index] = (self._steps[index][0], title)
        self._save()

    def advance(self) -> None:
        current = self._current()
        if current is None:
            return
        self._steps[current] = (StepWord.DONE, self._steps[current][1])
        if current + 1 < len(self._steps):
            self._steps[current + 1] = (StepWord.CURRENT, self._steps[current + 1][1])
        self._save()

    def end(self, word: StepWord) -> None:
        """Nothing newer to install: the stages after the check do not run."""
        self._steps = [(word, self._steps[0][1])]
        self._save()

    def fail(self) -> None:
        """The stage that broke is marked; the ones after it will not run."""
        current = self._current()
        if current is None:
            return
        self._steps = [*self._steps[:current], (StepWord.FAILED, self._steps[current][1])]
        self._save()

    def _current(self) -> int | None:
        return next((index for index, (word, _) in enumerate(self._steps) if word is StepWord.CURRENT), None)

    def _save(self) -> None:
        self._journal.write_steps(self._steps)


class StatusServers:
    """While the app is stopped, a small server answers the page on each of its ports with the update's
    progress (scripts/update_status_server.py). `where-to-go up` stops it by its pid file right before the
    app takes the port; every other way out stops it here.

    It runs on the base Python with the standard library only, outside the copy's virtual environment,
    which the update reinstalls under it."""

    def __init__(self, paths: ProjectPaths, python: str, log: UpdateLog) -> None:
        self._paths = paths
        self._python = python
        self._log = log
        self._running: dict[int, subprocess.Popen[bytes]] = {}

    def start(self, port: int) -> None:
        try:
            process = subprocess.Popen(
                [self._python, "-I", str(self._paths.status_server_script), "--port", str(port), "--host", HOST],
                cwd=self._paths.root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as error:
            self._log.say(f"The progress page could not start on port {port}: {error}")
            return
        self._running[port] = process
        pid_file = self._paths.status_server_pid(port)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(process.pid), encoding="utf-8")

    def stop_all(self) -> None:
        for port, process in self._running.items():
            pid_file = self._paths.status_server_pid(port)
            if pid_file.exists() and process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            pid_file.unlink(missing_ok=True)
        self._running.clear()


@dataclass(frozen=True)
class Release:
    tag: str
    version: tuple[int, int, int]

    PATTERN = re.compile(r"v(\d+)\.(\d+)\.(\d+)")

    @classmethod
    def latest(cls, tags: list[str]) -> Release | None:
        releases = [cls(tag, (int(m[1]), int(m[2]), int(m[3]))) for tag in tags if (m := cls.PATTERN.fullmatch(tag.strip()))]
        return max(releases, key=lambda release: release.version, default=None)


class Updater:
    MACOS_DIR = "macos"

    def __init__(
        self,
        paths: ProjectPaths,
        config: InstanceConfig,
        log: UpdateLog,
        cli: list[str] | None = None,
        package_sync: list[str] | None = None,
        apps: MacApps | None = None,
        macos: bool = sys.platform == "darwin",
        app_builder: list[str] | None = None,
        status_python: str | None = None,
    ) -> None:
        self._paths = paths
        self._config = config
        self._log = log
        self._journal = UpdateJournal(paths.root)
        self._stages = Stages(self._journal)
        self._cli = cli or python_command()
        self._package_sync = package_sync
        self._apps = apps or MacApps()
        self._macos = macos
        self._app_builder = app_builder or [str(paths.root / self.MACOS_DIR / "scripts" / "build-app.sh")]
        self._status = StatusServers(paths, status_python or getattr(sys, "_base_executable", "") or sys.executable, log)

    @classmethod
    def start_in_background(cls, paths: ProjectPaths, cli: list[str] | None = None) -> int:
        """Starts the update as a process of its own, outside the process tree of whoever asked: it stops and
        restarts the app, which must not take the update down with it. Writes the update's pid before it returns."""
        if not cls._lock_free(paths):
            raise UpdateFailedError("Another update is already running in this copy. Wait for it to finish.")
        paths.logs.mkdir(parents=True, exist_ok=True)
        with paths.update_log.open("a", encoding="utf-8") as log:
            process = subprocess.Popen(
                [*(cli or python_command()), "update", DETACHED_CHILD],
                cwd=paths.root,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log,
                env=child_environment(**NON_INTERACTIVE),
                **detached(),
            )
        UpdateJournal(paths.root).write_pid(process.pid)
        return process.pid

    def run(self) -> int:
        lock = self._lock(self._paths)
        self._log.start()
        try:
            lock.acquire(timeout=0)
        except Timeout:
            self._log.say("ERROR: another update is already running in this copy. Wait for it to finish.")
            return 1
        try:
            self._journal.write_pid(os.getpid())
            self._journal.write_state(UpdateWord.RUNNING)
            self._journal.write_error("")
            self._update()
            return 0
        except UpdateFailedError as error:
            return self._failed(str(error))
        except Exception as error:
            self._log.say(traceback.format_exc().rstrip())
            return self._failed(f"The update stopped on an unexpected error: {error}")
        finally:
            lock.release()

    def _failed(self, reason: str) -> int:
        self._stages.fail()
        self._log.say(f"ERROR: {reason}")
        self._journal.write_error(f"{reason}\n")
        self._finish(UpdateWord.FAILED)
        return 1

    def _update(self) -> None:
        self._stages.begin(CHECK, INSTALL, START)
        self._refuse_in_worktree()
        self._require_clean_tree()
        if self._log.run(["git", "fetch", "--tags", "--force", "origin"], self._paths.root) != 0:
            raise UpdateFailedError("Couldn't reach GitHub. Check your internet connection and try updating again.")
        release = Release.latest((self._git("tag", "--list", "v*") or "").split())
        if release is None:
            self._log.say("No release on origin yet. Nothing to update.")
            return self._nothing_to_do()
        if self._log.run(["git", "merge-base", "--is-ancestor", release.tag, "HEAD"], self._paths.root) == 0:
            self._log.say(f"Already up to date ({release.tag}).")
            return self._nothing_to_do()

        old_commit = self._git("rev-parse", "HEAD") or ""
        self._log.say(f"Updating to {release.tag}...")
        self._stages.rename(0, f"Downloading {release.tag}")
        self._stages.rename(1, f"Installing {release.tag}")
        self._stages.advance()

        servers = self._running_servers()
        self._call_cli(["down"], "Couldn't stop the app.")
        for server in servers:
            self._status.start(server.port)
        if self._log.run(["git", "checkout", "--quiet", release.tag], self._paths.root) != 0:
            raise UpdateFailedError(f"Couldn't switch to {release.tag} (git checkout).")
        self._rebuild_macos_app(old_commit, release.tag)
        self._install_packages()
        if any(server.ui is not None for server in servers) or self._paths.dist.is_dir():
            self._call_cli(["build"], "Couldn't build the new interface.")
        self._stages.advance()

        for server in servers:
            self._call_cli(["up", *server.arguments()], "Couldn't start the new version.")
        if not servers:
            self._log.say("The app wasn't running. Start it with: where-to-go up")
        self._stages.advance()
        self._log.say(f"Updated to {release.tag}.")
        self._finish(UpdateWord.DONE)

    def _nothing_to_do(self) -> None:
        self._stages.end(StepWord.DONE)
        self._finish(UpdateWord.DONE)

    def _finish(self, word: UpdateWord) -> None:
        self._status.stop_all()
        self._journal.write_state(word)

    def _refuse_in_worktree(self) -> None:
        if self._git("rev-parse", "--git-dir") != self._git("rev-parse", "--git-common-dir"):
            raise UpdateFailedError("Updating is for a copy cloned from GitHub, not for a git worktree. Run it in the main copy.")

    def _require_clean_tree(self) -> None:
        changes = self._git("status", "--porcelain", "--untracked-files=no")
        if changes is None:
            raise UpdateFailedError("This folder isn't a git copy of the app.")
        if changes.strip():
            self._log.say("ERROR: this copy has uncommitted changes:\n" + changes.rstrip())
            raise UpdateFailedError("This copy has uncommitted changes. Commit or discard them and try updating again.")

    def _running_servers(self) -> list[ServerSpec]:
        output = self._cli_output(["status", "--json"])
        try:
            servers = json.loads(output or "{}").get("servers", [])
            return [ServerSpec.from_json(server) for server in servers]
        except (ValueError, KeyError, AttributeError):
            self._log.say("Couldn't tell which servers run; none will be restarted.")
            return []

    def _rebuild_macos_app(self, old_commit: str, tag: str) -> None:
        if not self._macos or not self._apps.of(self._paths.root):
            return
        unchanged = self._log.run(["git", "diff", "--quiet", old_commit, tag, "--", self.MACOS_DIR], self._paths.root) == 0
        if unchanged:
            return
        menu_bar_icon = "1" if self._config.menu_bar_icon else "0"
        command = [*self._app_builder, str(self._paths.root), str(self._config.port), self._config.instance, menu_bar_icon]
        if self._log.run(command, self._paths.root) != 0:
            raise UpdateFailedError("Couldn't build the macOS app.")

    def _install_packages(self) -> None:
        if self._package_sync is None:
            try:
                self._package_sync = [str(Tools().uv()), "sync", "--frozen"]
            except ToolMissingError as error:
                raise UpdateFailedError(str(error)) from error
        if self._log.run(self._package_sync, self._paths.root) != 0:
            raise UpdateFailedError("Couldn't install the new version's packages (uv sync).")

    def _call_cli(self, arguments: list[str], failure: str) -> None:
        if self._log.run([*self._cli, *arguments], self._paths.root) != 0:
            raise UpdateFailedError(failure)

    def _cli_output(self, arguments: list[str]) -> str | None:
        return self._log.output([*self._cli, *arguments], self._paths.root)

    def _git(self, *arguments: str) -> str | None:
        output = self._log.output(["git", *arguments], self._paths.root)
        return output.strip() if output is not None else None

    @staticmethod
    def _lock(paths: ProjectPaths) -> FileLock:
        paths.pids.mkdir(parents=True, exist_ok=True)
        return FileLock(paths.update_lock)

    @classmethod
    def _lock_free(cls, paths: ProjectPaths) -> bool:
        lock = cls._lock(paths)
        try:
            lock.acquire(timeout=0)
        except Timeout:
            return False
        lock.release()
        return True
