from collections.abc import Callable, Iterator
from typing import Any, TypeAlias

import pytest

import flashpi._http as http_module
from tests.support import Api, Clock, Kind, Reply

MakeApi: TypeAlias = Callable[..., Api]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """A fake clock for the retries' waits, and no jitter: every backoff is the full delay."""
    fake = Clock()
    monkeypatch.setattr(http_module, "_monotonic", fake.monotonic)
    monkeypatch.setattr(http_module, "_sleep", fake.sleep)
    monkeypatch.setattr(http_module, "_async_sleep", fake.async_sleep)
    monkeypatch.setattr(http_module, "_random", lambda: 0.0)
    return fake


@pytest.fixture(params=["sync", "async"])
def kind(request: pytest.FixtureRequest) -> Kind:
    return request.param


@pytest.fixture
def make(kind: Kind, clock: Clock) -> Iterator[MakeApi]:
    """Builds a test client of the parametrized kind on a mocked API: make(*replies, **options)."""
    apis: list[Api] = []

    def build(*replies: Reply, **client_options: Any) -> Api:
        api = Api(kind, replies, **client_options)
        apis.append(api)
        return api

    yield build
    for api in apis:
        if api.sync is not None:
            api.sync.close()
