"""When the launcher rebuilds the interface: the main app and the phone page are one build."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from where_to_go.launcher.frontend import FrontendBuild
from where_to_go.launcher.paths import ProjectPaths
from where_to_go.launcher.tools import Tools

BUILT_AT = 2_000_000_000
EDITED_AT = BUILT_AT + 60


def touch(path: Path, moment: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (moment, moment))


@pytest.fixture
def paths(tmp_path: Path) -> ProjectPaths:
    paths = ProjectPaths(tmp_path / "copy")
    for source in ("src/main.tsx", "index.html", "phone.html", "package.json", "vite.config.ts", "vite.phone.config.ts"):
        touch(paths.frontend / source, BUILT_AT - 60)
    touch(paths.dist / "index.html", BUILT_AT)
    touch(paths.dist / "phone" / "phone.html", BUILT_AT)
    return paths


def build(paths: ProjectPaths) -> FrontendBuild:
    return FrontendBuild(paths, Tools(environ={}), say=lambda _: None)


def test_a_build_newer_than_its_sources_is_fresh(paths: ProjectPaths) -> None:
    assert not build(paths).is_stale()


def test_a_missing_phone_page_build_is_stale(paths: ProjectPaths) -> None:
    (paths.dist / "phone" / "phone.html").rename(paths.dist / "phone.html.old")

    assert build(paths).is_stale()


@pytest.mark.parametrize("source", ["phone.html", "vite.phone.config.ts"])
def test_an_edited_phone_page_source_makes_the_build_stale(paths: ProjectPaths, source: str) -> None:
    os.utime(paths.frontend / source, (EDITED_AT, EDITED_AT))

    assert build(paths).is_stale()
