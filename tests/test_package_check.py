"""The check of what `uv build` writes (scripts/package_check.py), on hand-made archives."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts import package_check

VERSION = "1.2.3"
METADATA = (
    f"Metadata-Version: 2.4\nName: flashpi\nVersion: {VERSION}\nRequires-Dist: httpx<1,>=0.27\n"
)
SOURCES = {
    "pyproject.toml": f'[project]\nname = "flashpi"\nversion = "{VERSION}"\n',
    "LICENSE": "MIT",
    "README.md": "# Flashpi",
    "README.en.md": "# Flashpi",
    "src/flashpi/__init__.py": "",
    "src/flashpi/py.typed": "",
    "src/flashpi/types/__init__.py": "",
    "tests/__init__.py": "",
    "tests/examples/typings/flask/__init__.pyi": "",
    "scripts/openapi.py": "",
    "openapi/openapi.json": "{}",
}


def wheel_files(metadata: str = METADATA) -> dict[str, str]:
    info = f"flashpi-{VERSION}.dist-info"
    return {
        "flashpi/__init__.py": "",
        "flashpi/py.typed": "",
        "flashpi/types/__init__.py": "",
        f"{info}/METADATA": metadata,
        f"{info}/WHEEL": "",
        f"{info}/RECORD": "",
        f"{info}/licenses/LICENSE": "MIT",
    }


def sdist_files() -> dict[str, str]:
    files = {f"flashpi-{VERSION}/{name}": text for name, text in SOURCES.items()}
    files[f"flashpi-{VERSION}/PKG-INFO"] = METADATA
    files[f"flashpi-{VERSION}/.gitignore"] = ""
    return files


def write_wheel(root: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(root / "dist" / f"flashpi-{VERSION}-py3-none-any.whl", "w") as wheel:
        for name, text in files.items():
            wheel.writestr(name, text)


def write_sdist(root: Path, files: dict[str, str]) -> None:
    with tarfile.open(root / "dist" / f"flashpi-{VERSION}.tar.gz", "w:gz") as sdist:
        for name, text in files.items():
            data = text.encode()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            sdist.addfile(member, io.BytesIO(data))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for name, text in SOURCES.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    cache = tmp_path / "src" / "flashpi" / "__pycache__" / "x.cpython-313.pyc"
    cache.parent.mkdir()
    cache.write_bytes(b"")
    (tmp_path / "dist").mkdir()
    write_wheel(tmp_path, wheel_files())
    write_sdist(tmp_path, sdist_files())
    return tmp_path


def test_a_complete_build_passes(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert package_check.main(root) == 0
    assert "hold what they should" in capsys.readouterr().out


def test_the_wheel_ships_the_package_only(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = wheel_files()
    del files["flashpi/py.typed"]
    files["tests/__init__.py"] = ""
    write_wheel(root, files)
    assert package_check.main(root) == 1
    errors = capsys.readouterr().err
    assert "Missing from the wheel: flashpi/py.typed" in errors
    assert "Unexpected in the wheel: tests/__init__.py" in errors


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        (METADATA.replace(VERSION, "9.9.9"), "says version 9.9.9, not 1.2.3"),
        (f"{METADATA}Requires-Dist: pydantic>=2\n", "must depend on httpx>=0.27,<1 only"),
        (METADATA.replace("Requires-Dist: httpx<1,>=0.27\n", ""), "only, not []"),
    ],
)
def test_the_wheel_metadata_has_the_version_and_httpx_only(
    root: Path, capsys: pytest.CaptureFixture[str], metadata: str, message: str
) -> None:
    write_wheel(root, wheel_files(metadata))
    assert package_check.main(root) == 1
    assert message in capsys.readouterr().err


def test_the_sdist_ships_what_the_tests_need(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = sdist_files()
    del files[f"flashpi-{VERSION}/openapi/openapi.json"]
    files[f"flashpi-{VERSION}/uv.lock"] = ""
    files["elsewhere/file.txt"] = ""
    write_sdist(root, files)
    assert package_check.main(root) == 1
    errors = capsys.readouterr().err
    assert "Missing from the sdist: openapi/openapi.json" in errors
    assert "Unexpected in the sdist: uv.lock" in errors
    assert "Outside flashpi-1.2.3/ in the sdist: elsewhere/file.txt" in errors


def test_dist_must_hold_one_build_of_this_version(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / "dist" / "flashpi-1.0.0-py3-none-any.whl").write_bytes(b"")
    assert package_check.main(root) == 1
    assert "dist/ must hold exactly flashpi-1.2.3-py3-none-any.whl" in capsys.readouterr().err
