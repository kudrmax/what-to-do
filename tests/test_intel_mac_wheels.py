import tomllib
from pathlib import Path

from packaging.requirements import Requirement

INTEL_MAC_CRYPTOGRAPHY = "48.0.1"


def test_dependencies_accept_the_last_cryptography_with_intel_mac_wheels():
    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    requirement = next(Requirement(line) for line in project["project"]["dependencies"] if line.startswith("cryptography"))
    assert requirement.specifier.contains(INTEL_MAC_CRYPTOGRAPHY)
