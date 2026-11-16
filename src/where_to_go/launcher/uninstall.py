from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from send2trash import send2trash

from where_to_go.launcher.control import ServerControl
from where_to_go.launcher.macos_apps import MacApps
from where_to_go.launcher.paths import ProjectPaths


class UninstallRefusedError(RuntimeError):
    pass


@dataclass
class UninstallReport:
    removed: list[Path] = field(default_factory=list)
    kept: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


class Uninstaller:
    """Takes the app off the computer, except the folder of the copy it runs from, which the user deletes
    last: a running program cannot delete its own folder on every platform.

    Stops the copy's servers, moves its macOS app and, when the user agrees, its data to the Trash."""

    def __init__(
        self,
        paths: ProjectPaths,
        control: ServerControl,
        data_dir: Path,
        apps: MacApps | None = None,
        trash: Callable[[str], None] = send2trash,
        say: Callable[[str], None] = print,
    ) -> None:
        self._paths = paths
        self._control = control
        self._data_dir = data_dir
        self._apps = apps or MacApps()
        self._trash = trash
        self._say = say

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    def apps(self) -> list[Path]:
        return self._apps.of(self._paths.root)

    def run(self, delete_data: bool) -> UninstallReport:
        report = UninstallReport()
        delete_data = delete_data and self._data_dir.exists()
        if delete_data:
            self._require_safe_data_dir()
        self._control.down()
        for app in self.apps():
            self._remove(app, report)
        if delete_data:
            self._remove(self._data_dir, report)
        elif self._data_dir.exists():
            report.kept.append(self._data_dir)
        return report

    def _remove(self, path: Path, report: UninstallReport) -> None:
        try:
            self._trash(str(path))
        except OSError as error:
            report.failed.append((path, str(error)))
            return
        report.removed.append(path)

    def _require_safe_data_dir(self) -> None:
        """A data folder set by hand could be anything; the folders that hold other things are never taken."""
        data = self._data_dir.resolve()
        guarded = {Path.home().resolve(), self._paths.root.resolve(), Path(data.anchor)}
        if data in guarded or any(data in path.parents for path in guarded):
            raise UninstallRefusedError(f"{data} holds more than the app's data; delete what you need from it by hand.")
