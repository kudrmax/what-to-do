import tomllib
from pathlib import Path

from packaging.requirements import Requirement

MACOS_WHEELS_FOR_BOTH_ARCHITECTURES = "19.0.2"


def test_dependencies_accept_the_pyav_with_wheels_for_both_macs():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    requirement = next(Requirement(line) for line in project["project"]["dependencies"] if line.startswith("av"))
    assert requirement.specifier.contains(MACOS_WHEELS_FOR_BOTH_ARCHITECTURES)


def test_the_disk_image_build_asks_for_the_macos_the_app_needs_so_pyav_wheels_fit():
    root = Path(__file__).parents[1]
    package = (root / "macos" / "Package.swift").read_text()
    script = (root / "macos" / "scripts" / "build-dmg.sh").read_text()
    assert ".macOS(.v14)" in package
    assert "export MACOSX_DEPLOYMENT_TARGET=14.0" in script
