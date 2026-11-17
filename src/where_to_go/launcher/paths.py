from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from where_to_go.launcher.bundle import AppBundle

PROJECT_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class ProjectPaths:
    """Where a copy of the app keeps its code, its build and what its running processes write.

    A git copy writes into its own folder. The app installed from the disk image writes into its state
    folder: the bundle stays as it was signed."""

    root: Path
    state: Path | None = None
    bundle: AppBundle | None = None

    @classmethod
    def here(cls) -> ProjectPaths:
        bundle = AppBundle.current()
        if bundle is not None:
            return cls(bundle.project, state=AppBundle.state_dir(), bundle=bundle)
        return cls(PROJECT_DIR)

    @property
    def writable(self) -> Path:
        return self.state or self.root

    @property
    def pids(self) -> Path:
        return self.writable / ".pids"

    @property
    def logs(self) -> Path:
        return self.writable / ".logs"

    @property
    def app_log(self) -> Path:
        return self.logs / "app.log"

    @property
    def update_log(self) -> Path:
        return self.logs / "update.log"

    @property
    def launcher_lock(self) -> Path:
        return self.pids / "launcher.lock"

    @property
    def update_lock(self) -> Path:
        return self.pids / "update.lock"

    @property
    def legacy_app_pid(self) -> Path:
        """Written by the shell `make up` of releases before 1.16."""
        return self.pids / "app.pid"

    @property
    def legacy_status_pid(self) -> Path:
        """Written by the shell updater of releases before 1.16."""
        return self.pids / "update_status.pid"

    @property
    def chosen_port(self) -> Path:
        """The port the copy moved to when another program held its own; it stays there."""
        return self.pids / "port"

    def server_record(self, port: int) -> Path:
        return self.pids / f"server-{port}.json"

    def server_records(self) -> list[Path]:
        return sorted(self.pids.glob("server-*.json"))

    def status_server_pid(self, port: int) -> Path:
        return self.pids / f"update_status-{port}.pid"

    @property
    def frontend(self) -> Path:
        return self.root / "frontend"

    @property
    def dist(self) -> Path:
        return self.frontend / "dist"

    @property
    def status_server_script(self) -> Path:
        return self.root / "scripts" / "update_status_server.py"

    @property
    def env_file(self) -> Path:
        return self.writable / ".env"

    @property
    def is_linked_worktree(self) -> bool:
        """A `git worktree add` copy has a .git file pointing at the main copy instead of a .git folder."""
        return (self.root / ".git").is_file()

    @property
    def cli(self) -> Path:
        """The command this copy's virtual environment installs."""
        if os.name == "nt":
            return self.root / ".venv" / "Scripts" / "where-to-go.exe"
        return self.root / ".venv" / "bin" / "where-to-go"


def python_command() -> list[str]:
    """Runs the app's command line with the interpreter of this environment, whatever the platform."""
    return [sys.executable, "-m", "where_to_go"]
