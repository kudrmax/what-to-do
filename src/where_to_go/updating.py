from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from where_to_go.launcher.paths import python_command
from where_to_go.launcher.processes import command_line, find_process
from where_to_go.launcher.spawning import child_environment
from where_to_go.launcher.spec import LegacyCommandLine
from where_to_go.launcher.update_journal import UpdateJournal
from where_to_go.launcher.updater import NON_INTERACTIVE


class UpdateState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    DONE = "done"


class UpdateStepStatus(StrEnum):
    DONE = "done"
    CURRENT = "current"
    PENDING = "pending"
    FAILED = "failed"


class UpdateStep(BaseModel):
    """One stage of the update as the user sees it, such as "Installing v1.2.0"."""

    title: str
    status: UpdateStepStatus


class UpdateProgress(BaseModel):
    """How the update started from the app is going. `log_tail` is what broke and the end of the log
    once it failed; `steps` are its stages in order, empty when unknown."""

    state: UpdateState
    log_tail: str = ""
    steps: list[UpdateStep] = []


class UpdateAlreadyRunningError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("An update is already running")


class UpdateFiles:
    """What the updater writes about its run in the project folder, read for the page."""

    STATE = UpdateJournal.STATE
    PID = UpdateJournal.PID
    ERROR = UpdateJournal.ERROR
    PROGRESS = UpdateJournal.PROGRESS
    LOG = UpdateJournal.LOG
    RUN_HEADERS = UpdateJournal.RUN_HEADERS
    LOG_TAIL_LINES = 40
    # Colours and cursor moves of uv and npm output, which a browser shows as garbage.
    ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

    def __init__(self, project_dir: Path) -> None:
        self._journal = UpdateJournal(project_dir)

    def state(self) -> UpdateState:
        try:
            return UpdateState(self.read(self.STATE).strip())
        except ValueError:
            return UpdateState.IDLE

    def write_state(self, state: UpdateState) -> None:
        self.write(self.STATE, state.value)

    def steps(self) -> list[UpdateStep]:
        """The stages from the progress file; none when it is missing or garbled."""
        steps = []
        for line in self.read(self.PROGRESS).splitlines():
            status, separator, title = line.partition(UpdateJournal.PROGRESS_SEPARATOR)
            if status not in UpdateStepStatus or not separator or not title.strip():
                return []
            steps.append(UpdateStep(title=title.strip(), status=UpdateStepStatus(status)))
        return steps

    def failure_report(self) -> str:
        """What broke as the updater summed it up, then the end of this run's log."""
        lines = self.read(self.LOG).splitlines()
        starts = [index for index, line in enumerate(lines) if line.startswith(self.RUN_HEADERS)]
        run = lines[starts[-1]:] if starts else lines
        parts = [part for part in (self.read(self.ERROR).strip(), "\n".join(run[-self.LOG_TAIL_LINES:])) if part]
        return self.ANSI_ESCAPE.sub("", "\n\n".join(parts))

    def read(self, relative_path: str) -> str:
        return self._journal.read(relative_path)

    def write(self, relative_path: str, text: str) -> None:
        self._journal.write(relative_path, text)


class UpdateProcess:
    """Tells the update's process from any other that got its pid since."""

    # The shell updater of releases before 1.16; it may still be finishing the update to this release.
    LEGACY_SCRIPT = "update.sh"
    COMMAND = "update"

    @classmethod
    def matches(cls, cmdline: list[str]) -> bool:
        if any(Path(part).name == cls.LEGACY_SCRIPT for part in cmdline):
            return True
        arguments = LegacyCommandLine.app_arguments(cmdline)
        return bool(arguments) and arguments[0] == cls.COMMAND


class UpdateRunner:
    """Starts the updater (`where-to-go update --background`) from the app and tells how it goes. The updater
    stops and restarts the app, so it runs as a process of its own, outside the app's process tree; it writes
    its pid before the start returns and ends by writing one word to the state file.

    The update is running while the process in the pid file is alive and is the updater; a pid file left by
    a run that died, or whose pid another process got since, does not count."""

    START_TIMEOUT_S = 60

    def __init__(
        self,
        project_dir: Path,
        command: list[str] | None = None,
        is_update: Callable[[list[str]], bool] = UpdateProcess.matches,
    ) -> None:
        self._project_dir = project_dir
        self._command = command or [*python_command(), "update", "--background"]
        self._is_update = is_update
        self._files = UpdateFiles(project_dir)
        # Two clicks at once must not both see the update as not running.
        self._starting = threading.Lock()

    def start(self) -> None:
        with self._starting:
            if self._progress().state is UpdateState.RUNNING:
                raise UpdateAlreadyRunningError
            self._spawn()

    def progress(self) -> UpdateProgress:
        with self._starting:
            return self._progress()

    def _progress(self) -> UpdateProgress:
        state = self._files.state()
        # The updater writes its last word before it exits: read again once it is gone.
        if state is UpdateState.RUNNING and not self._updater_alive():
            state = self._files.state()
            if state is UpdateState.RUNNING:
                self._files.write_state(UpdateState.FAILED)
                state = UpdateState.FAILED
        log_tail = self._files.failure_report() if state is UpdateState.FAILED else ""
        return UpdateProgress(state=state, log_tail=log_tail, steps=self._files.steps())

    def _spawn(self) -> None:
        self._files.write_state(UpdateState.RUNNING)
        self._files.write(UpdateFiles.ERROR, "")
        try:
            completed = subprocess.run(
                self._command,
                cwd=self._project_dir,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.START_TIMEOUT_S,
                env=child_environment(**NON_INTERACTIVE),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self._failed_to_start(f"The update didn't start: {error}")
            return
        if completed.returncode != 0:
            self._failed_to_start((completed.stderr or completed.stdout).strip() or "The update didn't start.")

    def _failed_to_start(self, reason: str) -> None:
        self._files.write(UpdateFiles.ERROR, reason)
        self._files.write_state(UpdateState.FAILED)

    def _updater_alive(self) -> bool:
        try:
            pid = int(self._files.read(UpdateFiles.PID).strip())
        except ValueError:
            return False
        process = find_process(pid)
        return process is not None and self._is_update(command_line(process))
