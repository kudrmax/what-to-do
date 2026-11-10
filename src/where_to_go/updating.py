from __future__ import annotations

import os
import re
import subprocess
import threading
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel


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
    """One stage of the update as the user sees it, such as "Устанавливаем v1.2.0"."""

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
        super().__init__("Обновление уже идёт")


class UpdateFiles:
    """What scripts/update.sh writes about its run, in the project folder."""

    STATE = ".pids/update.state"
    PID = ".pids/update.pid"
    ERROR = ".pids/update.error"
    # Rewritten whole on every change: one stage per line, its status, a tab, its title.
    PROGRESS = ".pids/update.progress"
    LOG = ".logs/update.log"
    # update.sh starts every run's log with this.
    RUN_HEADER = "=== make update"
    LOG_TAIL_LINES = 40
    # Colours and cursor moves of make and npm output, which a browser shows as garbage.
    ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir

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
            status, separator, title = line.partition("\t")
            if status not in UpdateStepStatus or not separator or not title.strip():
                return []
            steps.append(UpdateStep(title=title.strip(), status=UpdateStepStatus(status)))
        return steps

    def failure_report(self) -> str:
        """What broke as the script summed it up, then the end of this run's log."""
        lines = self.read(self.LOG).splitlines()
        starts = [index for index, line in enumerate(lines) if line.startswith(self.RUN_HEADER)]
        run = lines[starts[-1]:] if starts else lines
        parts = [part for part in (self.read(self.ERROR).strip(), "\n".join(run[-self.LOG_TAIL_LINES:])) if part]
        return self.ANSI_ESCAPE.sub("", "\n\n".join(parts))

    def read(self, relative_path: str) -> str:
        try:
            return (self._project_dir / relative_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def write(self, relative_path: str, text: str) -> None:
        path = self._project_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class UpdateRunner:
    """Runs scripts/update.sh in the project folder as a process of its own: the script stops and restarts
    the app, so it must outlive it. The script ends by writing one word to the state file.

    The update is running while the process in the pid file is alive and is update.sh; a pid file left by
    a run that died, or whose pid another process got since, does not count."""

    SCRIPT = "scripts/update.sh"
    NON_INTERACTIVE = {"GIT_TERMINAL_PROMPT": "0"}

    def __init__(self, project_dir: Path, script: str = SCRIPT) -> None:
        self._project_dir = project_dir
        self._script = script
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
        # The script writes its last word before it exits: read again once it is gone.
        if state is UpdateState.RUNNING and not self._script_alive():
            state = self._files.state()
            if state is UpdateState.RUNNING:
                self._files.write_state(UpdateState.FAILED)
                state = UpdateState.FAILED
        log_tail = self._files.failure_report() if state is UpdateState.FAILED else ""
        return UpdateProgress(state=state, log_tail=log_tail, steps=self._files.steps())

    def _spawn(self) -> None:
        (self._project_dir / UpdateFiles.LOG).parent.mkdir(parents=True, exist_ok=True)
        self._files.write_state(UpdateState.RUNNING)
        self._files.write(UpdateFiles.ERROR, "")
        try:
            process = subprocess.Popen(
                ["/bin/bash", self._script],
                cwd=self._project_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env={**os.environ, **self.NON_INTERACTIVE},
            )
        except OSError:
            self._files.write_state(UpdateState.FAILED)
            raise
        self._files.write(UpdateFiles.PID, str(process.pid))
        threading.Thread(target=process.wait, daemon=True).start()

    def _script_alive(self) -> bool:
        try:
            pid = int(self._files.read(UpdateFiles.PID).strip())
        except ValueError:
            return False
        result = subprocess.run(["/bin/ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, check=False)
        return os.path.basename(self._script) in result.stdout
