from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.tools import Tools


class BuildError(RuntimeError):
    pass


class FrontendBuild:
    """The interface is built once and again only when its sources change, so a start needs no Node.js
    when nothing changed."""

    SOURCES = (
        "src",
        "public",
        "index.html",
        "phone.html",
        "package.json",
        "package-lock.json",
        "vite.config.ts",
        "vite.phone.config.ts",
        "tsconfig.json",
        "tsconfig.app.json",
        "tsconfig.node.json",
    )
    OUTPUTS = (Path("index.html"), Path("phone") / "phone.html")
    DEPENDENCIES_STAMP = Path("node_modules") / ".package-lock.json"

    def __init__(self, paths: ProjectPaths, tools: Tools, say: Callable[[str], None] = print) -> None:
        self._paths = paths
        self._tools = tools
        self._say = say

    def is_stale(self) -> bool:
        outputs = [self._paths.dist / output for output in self.OUTPUTS]
        if not all(output.is_file() for output in outputs):
            return True
        return self._newest_source() > min(output.stat().st_mtime for output in outputs)

    def ensure(self) -> bool:
        """Builds the interface when it is missing or older than its sources; tells whether it built."""
        if not self.is_stale():
            return False
        npm = self._tools.npm()
        if self._dependencies_stale():
            self._say("Installing the interface's packages...")
            self._run(npm, ["ci", "--no-audit", "--no-fund"], "Couldn't install the interface's packages (npm ci).")
        self._say("Building the interface...")
        self._run(npm, ["run", "build"], "Couldn't build the interface (npm run build).")
        return True

    def _dependencies_stale(self) -> bool:
        stamp = self._paths.frontend / self.DEPENDENCIES_STAMP
        lock = self._paths.frontend / "package-lock.json"
        return not stamp.is_file() or stamp.stat().st_mtime < lock.stat().st_mtime

    def _newest_source(self) -> float:
        newest = 0.0
        for name in self.SOURCES:
            path = self._paths.frontend / name
            if path.is_file():
                newest = max(newest, path.stat().st_mtime)
            elif path.is_dir():
                newest = max([newest, *(file.stat().st_mtime for file in path.rglob("*") if file.is_file())])
        return newest

    def _run(self, npm: Path, arguments: list[str], failure: str) -> None:
        try:
            completed = subprocess.run(
                [str(npm), *arguments], cwd=self._paths.frontend, stdin=subprocess.DEVNULL, env=self._tools.environ_for(npm), check=False
            )
        except OSError as error:
            raise BuildError(f"{failure} {error}") from error
        if completed.returncode != 0:
            raise BuildError(failure)
