from __future__ import annotations

import plistlib
from pathlib import Path

PROJECT_DIR_KEY = "WTGProjectDir"


class MacApps:
    """The macOS apps `make app` installed for a copy: their Info.plist names the copy's folder."""

    def __init__(self, apps_dir: Path | None = None) -> None:
        self._apps_dir = apps_dir or Path.home() / "Applications"

    def of(self, project_dir: Path) -> list[Path]:
        if not self._apps_dir.is_dir():
            return []
        here = project_dir.resolve()
        return [app for app in sorted(self._apps_dir.glob("*.app")) if self._project_of(app) == here]

    @staticmethod
    def _project_of(app: Path) -> Path | None:
        try:
            with (app / "Contents" / "Info.plist").open("rb") as file:
                value = plistlib.load(file).get(PROJECT_DIR_KEY)
        except (OSError, plistlib.InvalidFileException, ValueError):
            return None
        if not isinstance(value, str) or not value:
            return None
        try:
            return Path(value).resolve(strict=True)
        except OSError:
            return None
