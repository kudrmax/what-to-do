from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path


class ToolMissingError(RuntimeError):
    pass


class Tools:
    """Finds the programs a copy needs besides Python, also when started from a desktop app whose PATH
    lacks the folders a terminal adds (Homebrew, nvm, Volta, uv's own)."""

    def __init__(self, environ: Mapping[str, str] = os.environ, home: Path | None = None) -> None:
        self._environ = environ
        self._home = home or Path.home()

    def uv(self) -> Path:
        named = self._environ.get("UV")
        if named and Path(named).is_file():
            return Path(named)
        found = self._find("uv", [self._home / ".local" / "bin", self._home / ".cargo" / "bin", *self._common_dirs()])
        if found is None:
            raise ToolMissingError("uv is not installed or not on PATH. Install it from https://docs.astral.sh/uv/ and try again.")
        return found

    def npm(self) -> Path:
        found = self._find("npm", self.program_dirs())
        if found is None:
            raise ToolMissingError("Node.js is needed to build the interface: install Node.js 20 or newer from https://nodejs.org and try again.")
        return found

    def program_dirs(self) -> list[Path]:
        """Where Node.js and the programs npm installs globally live, outside PATH."""
        return [*self._common_dirs(), self._home / ".volta" / "bin", *self._nvm_dirs()]

    def environ_for(self, tool: Path) -> dict[str, str]:
        """npm runs its scripts with `node`: the folder it came from goes first on PATH."""
        path = self._environ.get("PATH", "")
        return {**self._environ, "PATH": os.pathsep.join([str(tool.parent), path]) if path else str(tool.parent)}

    def _find(self, name: str, extra_dirs: list[Path]) -> Path | None:
        found = shutil.which(name, path=self._environ.get("PATH"))
        if found:
            return Path(found)
        extra = os.pathsep.join(str(directory) for directory in extra_dirs if directory.is_dir())
        found = shutil.which(name, path=extra) if extra else None
        return Path(found) if found else None

    def _common_dirs(self) -> list[Path]:
        if os.name == "nt":
            return [Path(self._environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs"]
        return [Path("/opt/homebrew/bin"), Path("/usr/local/bin"), Path("/usr/bin")]

    def _nvm_dirs(self) -> list[Path]:
        versions = self._home / ".nvm" / "versions" / "node"
        if not versions.is_dir():
            return []
        return [directory / "bin" for directory in sorted(versions.iterdir(), key=self._node_version, reverse=True)]

    @staticmethod
    def _node_version(directory: Path) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in directory.name.lstrip("v").split("."))
        except ValueError:
            return ()
