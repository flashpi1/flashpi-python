import re
import tomllib
from pathlib import Path

import flashpi

ROOT = Path(__file__).resolve().parent.parent


def test_the_version_matches_the_package_metadata() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == flashpi.VERSION
    assert flashpi.__version__ == flashpi.VERSION


def test_release_please_can_find_the_version() -> None:
    source = (ROOT / "src" / "flashpi" / "_version.py").read_text(encoding="utf-8")
    assert re.search(r'^VERSION = "[^"]+"  # x-release-please-version$', source, re.MULTILINE)


def test_the_package_is_typed() -> None:
    assert (ROOT / "src" / "flashpi" / "py.typed").is_file()
