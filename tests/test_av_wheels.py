import tomllib
from pathlib import Path

from packaging.requirements import Requirement

MACOS_WHEELS_FOR_BOTH_ARCHITECTURES = "19.0.2"


def test_dependencies_accept_the_pyav_with_wheels_for_both_macs():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    requirement = next(Requirement(line) for line in project["project"]["dependencies"] if line.startswith("av"))
    assert requirement.specifier.contains(MACOS_WHEELS_FOR_BOTH_ARCHITECTURES)
