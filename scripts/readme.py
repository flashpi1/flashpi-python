"""Keeps the README examples checked: every ```python block of README.md and README.en.md becomes a
module in tests/examples/readme/, which pyright and Ruff check with the rest of the repository.
Those modules are never run.

    uv run python scripts/readme.py generate  rewrite tests/examples/readme/ from the READMEs
    uv run python scripts/readme.py check     fail when it is out of date (the tests run it too)

A block must be a whole module that compiles on every supported Python: imports first, and no
`await` outside a function (wrap async code in a function run by asyncio.run). Names a block uses
without defining them, such as the `flashpi` client of "Getting started", are imported from
tests/examples/readme/_context.py; any other undefined name is an error.
"""

from __future__ import annotations

import ast
import builtins
import re
import symtable
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = Path("tests", "examples", "readme")
CONTEXT = EXAMPLES / "_context.py"
READMES = {"es": "README.md", "en": "README.en.md"}
"""Each README and the prefix of its modules."""

OPENING_FENCE = re.compile(r"^```\s*([\w+-]*)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")
PYTHON = frozenset({"python", "py"})


class ExampleError(Exception):
    """A README block that cannot become a checked module."""


@dataclass(frozen=True)
class Block:
    """A ```python block of a README."""

    readme: str
    line: int
    """Line of the opening fence (1-based)."""
    section: str
    """The heading the block sits under."""
    code: str


def python_blocks(readme: str, text: str) -> list[Block]:
    """The ```python blocks of a Markdown text, in order, each with the heading above it."""
    found: list[Block] = []
    section = ""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        fence = OPENING_FENCE.match(line)
        if fence is None:
            heading = HEADING.match(line)
            if heading:
                section = heading.group(1)
            index += 1
            continue
        start = index
        index += 1
        while index < len(lines) and lines[index].strip() != "```":
            index += 1
        if index == len(lines):
            raise ExampleError(f"{readme}:{start + 1}: the code block is never closed")
        if fence.group(1).lower() in PYTHON:
            code = "\n".join(lines[start + 1 : index])
            found.append(Block(readme, start + 1, section, f"{code}\n"))
        index += 1
    return found


def context_names(source: str) -> frozenset[str]:
    """The public names _context.py defines at module level."""
    names: set[str] = set()
    for statement in ast.parse(source).body:
        match statement:
            case ast.AnnAssign(target=ast.Name(id=name)):
                names.add(name)
            case ast.Assign(targets=targets):
                names.update(target.id for target in targets if isinstance(target, ast.Name))
            case (
                ast.FunctionDef(name=name)
                | ast.AsyncFunctionDef(name=name)
                | ast.ClassDef(name=name)
            ):
                names.add(name)
            case _:
                pass
    return frozenset(name for name in names if not name.startswith("_"))


def free_names(block: Block) -> set[str]:
    """Names the block uses at module level (or from its functions) without defining them."""
    location = f"{block.readme}:{block.line}"
    try:
        compile(block.code, location, "exec", dont_inherit=True)
    except SyntaxError as error:
        raise ExampleError(f"{location}: the example is not a valid module: {error.msg}") from error
    top = symtable.symtable(block.code, location, "exec")
    defined = {
        symbol.get_name()
        for symbol in top.get_symbols()
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace()
    }
    used: set[str] = set()
    pending = [top]
    while pending:
        table = pending.pop()
        for symbol in table.get_symbols():
            if symbol.is_referenced() and (table is top or symbol.is_global()):
                used.add(symbol.get_name())
        pending.extend(table.get_children())
    return {name for name in used - defined if not hasattr(builtins, name)}


def module(block: Block, number: int, available: frozenset[str]) -> str:
    """The checked module of a block: a header, then the block with its context imported."""
    if not block.code.strip():
        raise ExampleError(f"{block.readme}:{block.line}: the example is empty")
    needed = sorted(free_names(block))
    missing = [name for name in needed if name not in available]
    if missing:
        raise ExampleError(
            f"{block.readme}:{block.line}: the example uses {', '.join(missing)}, which neither "
            f"it nor {CONTEXT.as_posix()} defines"
        )
    lines = block.code.rstrip("\n").split("\n")
    if needed:
        statement = f"from .{CONTEXT.stem} import {', '.join(needed)}"
        body = ast.parse(block.code).body
        leading = 0
        while leading < len(body) and isinstance(body[leading], ast.Import | ast.ImportFrom):
            leading += 1
        if leading:
            end = body[leading - 1].end_lineno or body[leading - 1].lineno
            lines[end:end] = ["", statement]
        else:
            definition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            spacing = 2 if isinstance(body[0], definition) else 1
            lines[0:0] = [statement, *[""] * spacing]
    section = block.section.replace("\\", "/").replace('"', "'")
    header = [
        "# pyright: reportMissingModuleSource=false",
        f'"""Example {number} of {block.readme}, under "{section}".',
        "",
        "GENERATED by scripts/readme.py: edit the README, then run",
        "`uv run python scripts/readme.py generate`. Checked by pyright and Ruff, never run.",
        '"""',
        "",
    ]
    return "\n".join([*header, *lines]) + "\n"


def expected_modules(root: Path) -> dict[str, str]:
    """Every module tests/examples/readme/ should hold, by file name."""
    available = context_names((root / CONTEXT).read_text(encoding="utf-8"))
    modules: dict[str, str] = {}
    for prefix, readme in READMES.items():
        text = (root / readme).read_text(encoding="utf-8")
        for number, block in enumerate(python_blocks(readme, text), start=1):
            modules[f"{prefix}_{number:02d}.py"] = module(block, number, available)
    return modules


def generated_files(root: Path) -> list[Path]:
    """The modules currently in tests/examples/readme/ (everything but the context)."""
    names = re.compile(rf"^({'|'.join(READMES)})_\d+\.py$")
    return sorted(path for path in (root / EXAMPLES).glob("*.py") if names.match(path.name))


def main(argv: list[str], root: Path = ROOT) -> int:
    mode = argv[1] if len(argv) > 1 else "generate"
    if mode not in ("generate", "check") or len(argv) > 2:
        print("Usage: python scripts/readme.py generate|check", file=sys.stderr)
        return 2
    try:
        expected = expected_modules(root)
    except ExampleError as error:
        print(error, file=sys.stderr)
        return 1
    current = {path.name: path for path in generated_files(root)}
    if mode == "check":
        stale = sorted(
            name
            for name in expected.keys() | current.keys()
            if name not in current
            or name not in expected
            or current[name].read_text(encoding="utf-8") != expected[name]
        )
        if stale:
            print(
                f"{EXAMPLES.as_posix()} is out of date ({', '.join(stale)}). "
                "Run: uv run python scripts/readme.py generate",
                file=sys.stderr,
            )
            return 1
        print(f"{EXAMPLES.as_posix()} matches the READMEs ({len(expected)} examples)")
        return 0
    for name, path in current.items():
        if name not in expected:
            path.unlink()
    for name, text in expected.items():
        (root / EXAMPLES / name).write_text(text, encoding="utf-8")
    print(f"Wrote {len(expected)} examples to {EXAMPLES.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
