"""The timeout of an attempt is one deadline, from sending it to reading the whole answer, as the
Node SDK's AbortController: an answer that trickles in times out like one that never comes."""

import asyncio
import gzip
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest

from flashpi import APITimeoutError
from tests.support import AsyncTestClient, Clock, MockAPI, Reply, SyncTestClient, json_response

pytestmark = pytest.mark.anyio


class Trickle(httpx.SyncByteStream):
    """A sync answer body that takes `seconds` of the fake clock for each chunk."""

    def __init__(self, clock: Clock, chunks: list[bytes], seconds: float) -> None:
        self.clock = clock
        self.chunks = chunks
        self.seconds = seconds
        self.closed = False

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self.chunks:
            self.clock.advance(self.seconds)
            yield chunk

    def close(self) -> None:
        self.closed = True


class AsyncTrickle(httpx.AsyncByteStream):
    """An async answer body that really waits `seconds` before each chunk."""

    def __init__(self, chunks: list[bytes], seconds: float) -> None:
        self.chunks = chunks
        self.seconds = seconds
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            await asyncio.sleep(self.seconds)
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


BODY = [b'{"status"', b":", b'"operational"', b"}"]


def streamed(stream: httpx.SyncByteStream | httpx.AsyncByteStream) -> httpx.Response:
    return httpx.Response(200, stream=stream, headers={"content-type": "application/json"})


def sync_client(
    *replies: Reply, timeout: float, max_retries: int = 2
) -> tuple[SyncTestClient, MockAPI]:
    mock = MockAPI(replies)
    transport = httpx.MockTransport(mock.handler)  # pyright: ignore[reportArgumentType]
    http_client = httpx.Client(transport=transport)
    client = SyncTestClient(http_client=http_client, timeout=timeout, max_retries=max_retries)
    return client, mock


def async_client(
    *replies: Reply, timeout: float = 60, max_retries: int = 2
) -> tuple[AsyncTestClient, MockAPI]:
    mock = MockAPI(replies)
    transport = httpx.MockTransport(mock.handler)  # pyright: ignore[reportArgumentType]
    http_client = httpx.AsyncClient(transport=transport)
    client = AsyncTestClient(http_client=http_client, timeout=timeout, max_retries=max_retries)
    return client, mock


class TestOnFlashpi:
    def test_times_out_an_answer_that_trickles_in_past_the_deadline(self, clock: Clock) -> None:
        body = Trickle(clock, BODY, 0.4)
        client, mock = sync_client(streamed(body), timeout=1, max_retries=0)
        with pytest.raises(APITimeoutError, match="timed out after 1 seconds"):
            client.things.status()
        assert len(mock.sent) == 1
        assert body.closed
        assert clock.elapsed == 1.2

    def test_retries_it_with_the_same_idempotency_key(self, clock: Clock) -> None:
        slow = Trickle(clock, BODY, 0.6)
        client, mock = sync_client(streamed(slow), json_response({"ok": True}), timeout=1)
        assert client.things.issue({}) == {"ok": True}
        assert len(mock.sent) == 2
        assert len({request.headers["idempotency-key"] for request in mock.sent}) == 1
        assert clock.elapsed == 1.2 + 0.5

    def test_reads_an_answer_that_arrives_in_time(self, clock: Clock) -> None:
        body = Trickle(clock, BODY, 0.2)
        client, _ = sync_client(streamed(body), timeout=1)
        result = client.things.with_response.get("x")
        assert result.data == {"status": "operational"}
        assert result.response.content == b"".join(BODY)
        assert body.closed

    def test_decodes_a_compressed_answer_once(self, clock: Clock) -> None:
        compressed = gzip.compress(b"".join(BODY))
        chunks = [compressed[:10], compressed[10:]]
        answer = httpx.Response(
            200,
            stream=Trickle(clock, chunks, 0.1),
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        )
        client, _ = sync_client(answer, timeout=1)
        result = client.things.with_response.get("x")
        assert result.data == {"status": "operational"}
        assert result.response.content == b"".join(BODY)

    def test_times_out_an_answer_that_a_response_hook_of_your_client_read(
        self, clock: Clock
    ) -> None:
        body = Trickle(clock, BODY, 0.4)
        mock = MockAPI([streamed(body)])
        transport = httpx.MockTransport(mock.handler)  # pyright: ignore[reportArgumentType]

        def read_the_body(response: httpx.Response) -> None:
            response.read()

        hooks = {"response": [read_the_body]}
        http_client = httpx.Client(transport=transport, event_hooks=hooks)
        client = SyncTestClient(http_client=http_client, timeout=1, max_retries=0)
        with pytest.raises(APITimeoutError, match="timed out after 1 seconds"):
            client.things.status()
        assert len(mock.sent) == 1

    def test_times_out_an_empty_answer_whose_end_arrives_late(self, clock: Clock) -> None:
        late_end = Trickle(clock, [], 0)

        def answer(request: httpx.Request) -> httpx.Response:
            clock.advance(2)
            return streamed(late_end)

        client, _ = sync_client(answer, timeout=1, max_retries=0)
        with pytest.raises(APITimeoutError):
            client.things.status()


class TestOnAsyncFlashpi:
    async def test_times_out_an_answer_that_trickles_in_past_the_deadline(self) -> None:
        body = AsyncTrickle(BODY, 0.02)
        client, mock = async_client(streamed(body), timeout=0.05, max_retries=0)
        with pytest.raises(APITimeoutError, match=r"timed out after 0\.05 seconds"):
            await client.things.status()
        assert len(mock.sent) == 1
        assert body.closed

    async def test_reads_an_answer_that_arrives_in_time(self) -> None:
        client, _ = async_client(streamed(AsyncTrickle(BODY, 0.001)), timeout=5)
        result = await client.things.with_response.get("x")
        assert result.data == {"status": "operational"}
        assert result.response.content == b"".join(BODY)

    async def test_cancelling_the_task_while_the_answer_trickles_in_cancels_the_call(
        self,
    ) -> None:
        body = AsyncTrickle(BODY, 3600)
        client, mock = async_client(streamed(body), json_response({}))
        task = asyncio.create_task(client.things.status())
        while not mock.sent:
            await asyncio.sleep(0)
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        assert len(mock.sent) == 1
