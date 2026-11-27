from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class CliStatus(StrEnum):
    READY = "ready"
    MISSING = "missing"
    TOO_OLD = "too_old"


@dataclass(frozen=True)
class FoundCli:
    status: CliStatus
    path: Path | None
    version: str | None
    minimum: str
    update_command: str | None


class InstalledCli:
    """A command-line program the user installed: found on PATH first, as in a terminal, then in the folders
    its installers use, since an app started from Finder gets a PATH with system folders only.

    Its version is asked once per file: a new install or an update changes the file and is asked again."""

    VERSION_TIMEOUT_S = 5
    VERSION = re.compile(r"\d+\.\d+\.\d+")

    def __init__(
        self,
        name: str,
        minimum: str,
        extra_dirs: Callable[[], list[Path]],
        environ: Mapping[str, str] = os.environ,
        run_version: Callable[[Path], str | None] | None = None,
    ) -> None:
        self._name = name
        self._minimum = minimum
        self._extra_dirs = extra_dirs
        self._environ = environ
        self._run_version = run_version or self._ask_version
        self._versions: dict[tuple[Path, int], str | None] = {}

    def find(self) -> FoundCli:
        path = self._locate()
        if path is None:
            return FoundCli(CliStatus.MISSING, None, None, self._minimum, None)
        version = self._version(path)
        status = CliStatus.READY if version is not None and self._parts(version) >= self._parts(self._minimum) else CliStatus.TOO_OLD
        return FoundCli(status, path, version, self._minimum, self._update_command(path))

    def _locate(self) -> Path | None:
        for search in (self._environ.get("PATH", ""), os.pathsep.join(str(directory) for directory in self._extra_dirs())):
            found = shutil.which(self._name, path=search) if search else None
            if found:
                return Path(found)
        return None

    def _version(self, path: Path) -> str | None:
        resolved = path.resolve()
        key = (resolved, resolved.stat().st_mtime_ns)
        if key not in self._versions:
            match = self.VERSION.search(self._run_version(path) or "")
            self._versions[key] = match.group(0) if match else None
        return self._versions[key]

    def _update_command(self, path: Path) -> str:
        parts = path.resolve().parts
        if "Caskroom" in parts[:-1]:
            return f"brew upgrade --cask {parts[parts.index('Caskroom') + 1]}"
        return f"{Path(self._name).stem} update"

    def _ask_version(self, path: Path) -> str | None:
        try:
            done = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                timeout=self.VERSION_TIMEOUT_S,
                stdin=subprocess.DEVNULL,
                env=dict(self._environ),
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout if done.returncode == 0 else None

    @staticmethod
    def _parts(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))
