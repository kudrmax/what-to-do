"""The app as installed from the macOS disk image. Python, the packages and the built interface live inside
`What To Do.app`, which the app never writes to: it would break the bundle's signature. What the copy
writes about itself (pid records, logs, the update journal, `.env`) goes to its state folder instead.

Imports only the standard library: the updater relies on it while it replaces the bundle under itself."""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MARKER = "bundle.json"
STATE_DIR_ENV = "WHERE_TO_GO_STATE_DIR"
STATE_DIR_NAME = "What To Do"
GITHUB_REPO = "kudrmax/what-to-do"


class DiskImageName:
    """The disk image of a release for one kind of Mac, as the release workflow names it."""

    LABELS = {"arm64": "Apple-Silicon", "x86_64": "Intel"}

    def __init__(self, arch: str) -> None:
        if arch not in self.LABELS:
            raise ValueError(f"No disk image is built for {arch!r} Macs")
        self.arch = arch

    def of(self, version: str) -> str:
        return f"What-To-Do-{version}-{self.LABELS[self.arch]}.dmg"


@dataclass(frozen=True)
class AppBundle:
    """`What To Do.app/Contents/Resources` holds `python` (the runtime with the app's packages) and
    `project` (the built interface, the changelog and the marker file naming the bundle's architecture)."""

    app: Path
    arch: str

    @classmethod
    def current(cls, prefix: Path | None = None) -> AppBundle | None:
        """The bundle this Python runs from, or None for a git copy."""
        python_home = prefix or Path(sys.prefix)
        marker = python_home.parent / "project" / MARKER
        try:
            arch = json.loads(marker.read_text(encoding="utf-8"))["arch"]
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return cls(app=python_home.parents[2], arch=str(arch))

    @property
    def resources(self) -> Path:
        return self.app / "Contents" / "Resources"

    @property
    def project(self) -> Path:
        return self.resources / "project"

    @property
    def python(self) -> Path:
        return self.resources / "python" / "bin" / "python3"

    @property
    def image(self) -> DiskImageName:
        return DiskImageName(self.arch)

    @staticmethod
    def state_dir(environ: Mapping[str, str] = os.environ) -> Path:
        named = environ.get(STATE_DIR_ENV, "").strip()
        if named:
            return Path(named).expanduser().resolve()
        return Path.home() / "Library" / "Application Support" / STATE_DIR_NAME
