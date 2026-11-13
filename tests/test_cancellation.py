"""Cancelling calls: task cancellation on AsyncFlashpi (Node: the `signal` option), and
KeyboardInterrupt on Flashpi. Neither is wrapped, retried or given an Idempotency-Key."""

import asyncio

import httpx
import pytest

import flashpi._http as http_module
from tests.support import AsyncTestClient, MockAPI, Reply, SyncTestClient, json_response, problem

pytestmark = pytest.mark.anyio


def async_client(*replies: Reply) -> tuple[AsyncTestClient, MockAPI]:
    mock = MockAPI(replies)
    transport = httpx.MockTransport(mock.handler)  # pyright: ignore[reportArgumentType]
    return AsyncTestClient(http_client=httpx.AsyncClient(transport=transport)), mock


async def test_cancels_a_request_in_flight_without_retrying_it() -> None:
    sent = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        sent.set()
        await asyncio.Event().wait()
        raise AssertionError("never answered")

    client, mock = async_client(hang, json_response({}))
    task = asyncio.create_task(client.things.issue({}, idempotency_key="order-2"))
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert len(mock.sent) == 1


async def test_stops_waiting_between_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeping = asyncio.Event()

    async def sleep(seconds: float) -> None:
        sleeping.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(http_module, "_async_sleep", sleep)
    client, mock = async_client(problem(500, "internal_error"), json_response({}))
    task = asyncio.create_task(client.things.status())
    await sleeping.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(mock.sent) == 1


async def test_a_timeout_around_the_call_cancels_it() -> None:
    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        raise AssertionError("never answered")

    client, mock = async_client(hang)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await client.things.status()
    assert len(mock.sent) == 1


def test_lets_a_keyboard_interrupt_through_without_retrying() -> None:
    mock = MockAPI([KeyboardInterrupt(), json_response({})])
    client = SyncTestClient(http_client=httpx.Client(transport=httpx.MockTransport(mock.handler)))  # pyright: ignore[reportArgumentType]
    with pytest.raises(KeyboardInterrupt):
        client.things.issue({}, idempotency_key="order-3")
    assert len(mock.sent) == 1
