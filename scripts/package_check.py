"""Checks what `uv build` wrote to dist/ before it goes to PyPI. Fails on anything missing or
anything else.

    uv build && uv run python scripts/package_check.py

- The wheel holds the flashpi package (every module of src/flashpi and its py.typed marker), the
  license and the metadata, and nothing else: no tests, scripts or caches.
- The sdist holds the package sources plus what its tests need (tests, scripts, the OpenAPI
  document, the READMEs), so the tests can run from it.
- Both carry the version of pyproject.toml, and the wheel depends on httpx only.
"""

from __future__ import annotations

import sys
import tarfile
import tomllib
import zipfile
from email.parser import HeaderParser
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = Path("src", "flashpi")
SDIST_REQUIRED = ["LICENSE", "PKG-INFO", "README.en.md", "README.md", "pyproject.toml"]
SDIST_OPTIONAL = [".gitignore", "CHANGELOG.md"]
SDIST_TREES = {
    "openapi": (".json",),
    "scripts": (".py",),
    "tests": (".py", ".pyi"),
}
"""Directories the sdist carries for its tests, with the file types they may hold."""


def package_files(root: Path) -> list[str]:
    """The files of the package, relative to src/: its modules and py.typed."""
    source = root / PACKAGE
    files = [
        path
        for path in source.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix == ".py" or path.name == "py.typed")
    ]
    return sorted(path.relative_to(root / "src").as_posix() for path in files)


def compare(kind: str, found: list[str], required: list[str], optional: list[str]) -> list[str]:
    missing = sorted(set(required) - set(found))
    extra = sorted(set(found) - set(required) - set(optional))
    problems = [f"Missing from the {kind}: {name}" for name in missing]
    problems += [f"Unexpected in the {kind}: {name}" for name in extra]
    return problems


def check_wheel(path: Path, root: Path, version: str) -> list[str]:
    info = f"flashpi-{version}.dist-info"
    with zipfile.ZipFile(path) as wheel:
        names = [name for name in wheel.namelist() if not name.endswith("/")]
        metadata = HeaderParser().parsestr(wheel.read(f"{info}/METADATA").decode("utf-8"))
    required = package_files(root) + [
        f"{info}/{name}" for name in ("METADATA", "RECORD", "WHEEL", "licenses/LICENSE")
    ]
    problems = compare("wheel", names, required, [])
    if metadata["Version"] != version:
        problems.append(f"The wheel's metadata says version {metadata['Version']}, not {version}")
    requires = metadata.get_all("Requires-Dist") or []
    if [requirement.split(";")[0].replace(" ", "") for requirement in requires] != [
        "httpx<1,>=0.27"
    ]:
        problems.append(f"The wheel must depend on httpx>=0.27,<1 only, not {requires}")
    return problems


def check_sdist(path: Path, root: Path, version: str) -> list[str]:
    top = PurePosixPath(f"flashpi-{version}")
    with tarfile.open(path) as sdist:
        members = [member for member in sdist.getmembers() if member.isfile()]
    found: list[str] = []
    problems: list[str] = []
    for member in members:
        name = PurePosixPath(member.name)
        if not name.is_relative_to(top):
            problems.append(f"Outside {top}/ in the sdist: {member.name}")
            continue
        found.append(name.relative_to(top).as_posix())
    required = SDIST_REQUIRED + [f"src/{name}" for name in package_files(root)]
    for directory, suffixes in SDIST_TREES.items():
        tracked = sorted(
            path.relative_to(root).as_posix()
            for path in (root / directory).rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix in suffixes
        )
        required += tracked
    return problems + compare("sdist", found, required, SDIST_OPTIONAL)


def main(root: Path = ROOT) -> int:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version: str = project["version"]
    dist = root / "dist"
    wheels = sorted(dist.glob("flashpi-*.whl"))
    sdists = sorted(dist.glob("flashpi-*.tar.gz"))
    expected_wheel = dist / f"flashpi-{version}-py3-none-any.whl"
    expected_sdist = dist / f"flashpi-{version}.tar.gz"
    if wheels != [expected_wheel] or sdists != [expected_sdist]:
        print(
            f"dist/ must hold exactly {expected_wheel.name} and {expected_sdist.name}; run "
            "`uv build` on a clean dist/",
            file=sys.stderr,
        )
        return 1
    problems = check_wheel(expected_wheel, root, version) + check_sdist(
        expected_sdist, root, version
    )
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"{expected_wheel.name} and {expected_sdist.name} hold what they should")
    return 0


if __name__ == "__main__":
    sys.exit(main())
