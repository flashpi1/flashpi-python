"""Uses the installed wheel the way an application would. CI runs it with a clean virtual
environment that holds only the wheel and httpx:

    uv venv /tmp/clean && uv pip install --python /tmp/clean/bin/python dist/*.whl
    /tmp/clean/bin/python scripts/installed_check.py

It fails when flashpi is imported from this repository instead of the installed wheel, when the
wheel lacks its typing marker or its version, or when a call through each client does not work.
"""

from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.resources
import sys
from pathlib import Path

import httpx

import flashpi
from flashpi import AsyncFlashpi, Flashpi

ROOT = Path(__file__).resolve().parent.parent
KEY = "fp_test_installed_check"


def answer(request: httpx.Request) -> httpx.Response:
    if request.url.path != "/v1/status" or request.headers.get("authorization") != f"Bearer {KEY}":
        return httpx.Response(404, json={"title": "Not found"})
    return httpx.Response(200, json={"status": "operational"})


async def async_status() -> str:
    async with (
        httpx.AsyncClient(transport=httpx.MockTransport(answer)) as http_client,
        AsyncFlashpi(KEY, http_client=http_client) as client,
    ):
        return (await client.status.get())["status"]


def main() -> int:
    location = Path(flashpi.__file__).resolve()
    if location.is_relative_to(ROOT / "src"):
        print(f"flashpi was imported from {location.parent}, not from a wheel", file=sys.stderr)
        return 1
    version = importlib.metadata.version("flashpi")
    problems: list[str] = []
    if flashpi.__version__ != version:
        problems.append(f"flashpi.__version__ is {flashpi.__version__}, the wheel {version}")
    if not importlib.resources.files("flashpi").joinpath("py.typed").is_file():
        problems.append("py.typed is missing")
    with (
        httpx.Client(transport=httpx.MockTransport(answer)) as http_client,
        Flashpi(KEY, http_client=http_client) as client,
    ):
        if client.status.get()["status"] != "operational":
            problems.append("Flashpi did not read the status")
    if asyncio.run(async_status()) != "operational":
        problems.append("AsyncFlashpi did not read the status")
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    print(f"flashpi {version} works from {location.parent} on Python {sys.version.split()[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
