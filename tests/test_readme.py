"""The README examples: tests/examples/readme/ must hold every ```python block of both READMEs, as
modules pyright and Ruff check (scripts/readme.py)."""

from pathlib import Path

import pytest

from scripts import readme
from scripts.readme import Block, ExampleError, context_names, free_names, module, python_blocks

ROOT = Path(__file__).resolve().parent.parent
CONTEXT = '''"""Stand-ins."""

from flashpi import Flashpi

flashpi: Flashpi
'''
HEADER_LINES = 7


def block(code: str) -> Block:
    return Block("README.en.md", 3, "Getting started", code)


def body_of(text: str) -> str:
    """A generated module without its header."""
    return "\n".join(text.split("\n")[HEADER_LINES:])


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / readme.EXAMPLES).mkdir(parents=True)
    (tmp_path / readme.CONTEXT).write_text(CONTEXT, encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Flashpi\n\n## Estado\n\n```python\nprint(flashpi.status.get())\n```\n",
        encoding="utf-8",
    )
    (tmp_path / "README.en.md").write_text(
        "# Flashpi\n\n```bash\npip install flashpi\n```\n\n## Status\n\n"
        "```python\nimport os\n\nprint(os.sep, flashpi)\n```\n\n"
        "```python\nprint(1)\n```\n",
        encoding="utf-8",
    )
    return tmp_path


def test_the_committed_examples_match_the_readmes(capsys: pytest.CaptureFixture[str]) -> None:
    assert readme.main(["readme.py", "check"]) == 0
    assert "matches the READMEs" in capsys.readouterr().out


def test_bad_arguments_are_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert readme.main(["readme.py", "publish"]) == 2
    assert readme.main(["readme.py", "check", "extra"]) == 2
    assert "Usage" in capsys.readouterr().err


def test_generate_writes_one_module_per_block_and_check_follows_the_readmes(
    root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert readme.main(["readme.py", "check"], root) == 1
    assert "es_01.py" in capsys.readouterr().err

    assert readme.main(["readme.py"], root) == 0
    names = sorted(path.name for path in (root / readme.EXAMPLES).iterdir())
    assert names == ["_context.py", "en_01.py", "en_02.py", "es_01.py"]
    assert readme.main(["readme.py", "check"], root) == 0

    (root / "README.en.md").write_text("# Flashpi\n\n```python\nprint(2)\n```\n", encoding="utf-8")
    assert readme.main(["readme.py", "check"], root) == 1
    assert "en_01.py, en_02.py" in capsys.readouterr().err
    assert readme.main(["readme.py", "generate"], root) == 0
    assert not (root / readme.EXAMPLES / "en_02.py").exists()
    assert (root / readme.CONTEXT).exists()
    assert readme.main(["readme.py", "check"], root) == 0


def test_a_broken_example_fails_both_modes(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (root / "README.md").write_text("```python\nprint(undefined_name)\n```\n", encoding="utf-8")
    assert readme.main(["readme.py", "generate"], root) == 1
    assert readme.main(["readme.py", "check"], root) == 1
    assert "README.md:1: the example uses undefined_name" in capsys.readouterr().err


def test_blocks_carry_their_heading_and_other_languages_are_skipped() -> None:
    text = (
        "# Flashpi\n\n## Webhooks\n\n```bash\npip install flashpi\n```\n\n"
        "```python\n# A comment, not a heading\nprint(1)\n```\n\n### Thin mode\n\n"
        "```py\nprint(2)\n```\n\n```\nplain\n```\n"
    )
    blocks = python_blocks("README.en.md", text)
    assert [(found.line, found.section, found.code) for found in blocks] == [
        (9, "Webhooks", "# A comment, not a heading\nprint(1)\n"),
        (16, "Thin mode", "print(2)\n"),
    ]


def test_an_unclosed_block_is_an_error() -> None:
    with pytest.raises(ExampleError, match=r"README\.md:2: the code block is never closed"):
        python_blocks("README.md", "Text\n```python\nprint(1)\n")


def test_the_context_names_are_its_public_module_level_names() -> None:
    source = (
        "import os\nfrom x import y\n\nflashpi: int\nbody = 1\nfirst, second = 1, 2\n"
        "_private: int\n\n\ndef helper() -> None: ...\n\n\nasync def fetch() -> None: ...\n\n\n"
        "class Order: ...\n\n\nif True:\n    hidden = 1\n"
    )
    assert context_names(source) == {"flashpi", "body", "helper", "fetch", "Order"}


def test_free_names_are_the_names_the_block_never_defines() -> None:
    code = """import os
from json import dumps as to_json

value = 1


def view(request: Request) -> None:
    local = flashpi.status.get()
    print(local, os.sep, to_json, value, [item for item in invoice])


class Handler:
    kind = order


try:
    pass
except ValueError as error:
    print(error)
with open("f") as stream:
    print(stream)
for index in range(2):
    print(index, len(body))
"""
    assert free_names(block(code)) == {"Request", "flashpi", "invoice", "order", "body"}


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("await flashpi.status.get()\n", "not a valid module: 'await' outside function"),
        ("print(\n", "not a valid module"),
        ("\n\n", "the example is empty"),
        ("print(flashpi, undefined)\n", "uses undefined, which neither it nor"),
    ],
)
def test_examples_that_cannot_be_checked_are_errors(code: str, message: str) -> None:
    with pytest.raises(ExampleError, match=message):
        module(block(code), 1, frozenset({"flashpi"}))


def test_the_context_is_imported_after_the_imports_of_the_block() -> None:
    code = "import os\n\nfrom flashpi import Flashpi\n\nprint(os.sep, Flashpi, invoice, flashpi)\n"
    text = module(block(code), 2, frozenset({"flashpi", "invoice"}))
    assert text.startswith(
        "# pyright: reportMissingModuleSource=false\n"
        '"""Example 2 of README.en.md, under "Getting started".\n'
    )
    assert body_of(text) == (
        "import os\n\nfrom flashpi import Flashpi\n\nfrom ._context import flashpi, invoice\n\n"
        "print(os.sep, Flashpi, invoice, flashpi)\n"
    )


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("print(flashpi)\n", "from ._context import flashpi\n\nprint(flashpi)\n"),
        (
            "def show() -> None:\n    print(flashpi)\n",
            "from ._context import flashpi\n\n\ndef show() -> None:\n    print(flashpi)\n",
        ),
        (
            "class Show:\n    client = flashpi\n",
            "from ._context import flashpi\n\n\nclass Show:\n    client = flashpi\n",
        ),
        ("import os\n\nprint(os.sep)\n", "import os\n\nprint(os.sep)\n"),
    ],
)
def test_the_context_import_opens_a_block_without_imports_and_only_when_needed(
    code: str, expected: str
) -> None:
    assert body_of(module(block(code), 1, frozenset({"flashpi"}))) == expected


def test_quotes_in_a_heading_do_not_break_the_docstring() -> None:
    text = module(Block("README.md", 1, 'Say "hi" \\ bye', "print(1)\n"), 1, frozenset())
    assert """under "Say 'hi' / bye".""" in text
