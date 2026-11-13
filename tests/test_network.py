"""The deadline of an attempt on the network itself, which MockTransport cannot show: on
`Flashpi`, the httpx client the SDK creates limits every network operation to the time the
attempt has left (`flashpi._network`), as `asyncio.timeout()` does on `AsyncFlashpi` and the
AbortController in Node. Answers come from a local server on a thread."""

import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterator
from types import TracebackType
from typing import Any

import httpcore
import httpx
import pytest

from flashpi import APITimeoutError, AsyncFlashpi, Flashpi
from flashpi._network import (
    WRITE_PIECE,
    DeadlineBackend,
    DeadlineNetworkStream,
    attempt_deadline,
)
from tests.support import TEST_KEY

pytestmark = pytest.mark.anyio

Answer = Callable[[socket.socket], None]

BODY = b'{"status":"operational"}'
PROXY_VARIABLES = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]


REST = (
    b"Content-Type: application/json\r\n" + f"Content-Length: {len(BODY)}\r\n\r\n".encode() + BODY
)
"""What follows the status line and the X-Pad header."""


def answer_at_once(connection: socket.socket) -> None:
    connection.sendall(b"HTTP/1.1 200 OK\r\n" + REST)


def trickle_the_headers(seconds: float) -> Answer:
    """The status line at once, then one byte of a header every 20 ms for `seconds`."""

    def answer(connection: socket.socket) -> None:
        connection.sendall(b"HTTP/1.1 200 OK\r\nX-Pad: ")
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            connection.sendall(b"a")
            time.sleep(0.02)
        connection.sendall(b"\r\n" + REST)

    return answer


class LocalServer:
    """An HTTP/1.1 server on 127.0.0.1 that answers every request with `answer`."""

    def __init__(self, answer: Answer) -> None:
        self.answer = answer
        self.heads: list[bytes] = []
        self.connections = 0
        self._stop = threading.Event()
        self._listener = socket.create_server(("127.0.0.1", 0))
        self._listener.settimeout(0.05)
        self.url = f"http://127.0.0.1:{self._listener.getsockname()[1]}"
        self._threads: list[threading.Thread] = []

    def __enter__(self) -> "LocalServer":
        self._start(self._accept)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop.set()
        for thread in list(self._threads):
            thread.join(10)
        self._listener.close()

    def _start(self, target: Callable[..., None], *args: object) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        self._threads.append(thread)
        thread.start()

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._listener.accept()
            except TimeoutError:
                continue
            self.connections += 1
            self._start(self._serve, connection)

    def _serve(self, connection: socket.socket) -> None:
        connection.settimeout(5)
        with connection:
            try:
                while not self._stop.is_set():
                    head = b""
                    while b"\r\n\r\n" not in head:
                        data = connection.recv(65536)
                        if not data:
                            return
                        head += data
                    self.heads.append(head)
                    self.answer(connection)
            except OSError:
                return


@pytest.fixture(autouse=True)
def no_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)


class TestHeadersThatTrickleIn:
    def test_time_out_on_flashpi(self) -> None:
        with (
            LocalServer(trickle_the_headers(3)) as server,
            Flashpi(TEST_KEY, base_url=server.url, timeout=0.3, max_retries=0) as client,
        ):
            started = time.monotonic()
            with pytest.raises(APITimeoutError, match=r"timed out after 0\.3 seconds") as caught:
                client.status.get()
            assert time.monotonic() - started < 1.5
            assert isinstance(caught.value.__cause__, httpx.ReadTimeout)

    async def test_time_out_on_async_flashpi(self) -> None:
        with LocalServer(trickle_the_headers(3)) as server:
            async with AsyncFlashpi(
                TEST_KEY, base_url=server.url, timeout=0.3, max_retries=0
            ) as client:
                started = time.monotonic()
                with pytest.raises(APITimeoutError, match=r"timed out after 0\.3 seconds"):
                    await client.status.get()
                assert time.monotonic() - started < 1.5

    def test_time_out_through_a_proxy_of_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with LocalServer(trickle_the_headers(3)) as proxy:
            monkeypatch.setenv("HTTP_PROXY", proxy.url)
            base_url = "http://api.flashpi.test"
            with Flashpi(TEST_KEY, base_url=base_url, timeout=0.3, max_retries=0) as client:
                started = time.monotonic()
                with pytest.raises(APITimeoutError):
                    client.status.get()
                assert time.monotonic() - started < 1.5
            assert proxy.heads[0].startswith(b"GET http://api.flashpi.test/v1/status HTTP/1.1")


class TestTheSDKsOwnClient:
    def test_answers_in_time_and_reuses_the_connection(self) -> None:
        with (
            LocalServer(answer_at_once) as server,
            Flashpi(TEST_KEY, base_url=server.url, timeout=5) as client,
        ):
            assert client.status.get() == {"status": "operational"}
            assert client.status.get() == {"status": "operational"}
        assert server.connections == 1
        assert len(server.heads) == 2

    def test_gives_the_backend_to_its_pools_and_those_of_the_proxies(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pins the private attributes of httpx and httpcore the SDK sets (flashpi._network).
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
        monkeypatch.setenv("NO_PROXY", "example.com")
        with Flashpi(TEST_KEY) as client:
            http_client = client._http_client  # pyright: ignore[reportPrivateUsage]
            mounts = list(http_client._mounts.values())  # pyright: ignore[reportPrivateUsage]
            transports = [http_client._transport, *mounts]  # pyright: ignore[reportPrivateUsage]
            pools = [
                transport._pool  # pyright: ignore[reportPrivateUsage]
                for transport in transports
                if isinstance(transport, httpx.HTTPTransport)
            ]
            assert None in mounts
            assert len(pools) == 2
            assert isinstance(pools[1], httpcore.HTTPProxy)
            for pool in pools:
                backend = pool._network_backend  # pyright: ignore[reportPrivateUsage]
                assert isinstance(backend, DeadlineBackend)

    def test_leaves_your_http_client_as_it_is(self) -> None:
        with httpx.Client() as yours:
            Flashpi(TEST_KEY, http_client=yours)
            transport = yours._transport  # pyright: ignore[reportPrivateUsage]
            assert isinstance(transport, httpx.HTTPTransport)
            backend = transport._pool._network_backend  # pyright: ignore[reportPrivateUsage]
            assert type(backend) is httpcore.SyncBackend


class FakeStream(httpcore.NetworkStream):
    """A connection that records what it is asked to do."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        self.calls.append(("read", max_bytes, timeout))
        return b"data"

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.calls.append(("write", len(buffer), timeout))

    def close(self) -> None:
        self.calls.append(("close",))

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        self.calls.append(("start_tls", server_hostname, timeout))
        return FakeStream()

    def get_extra_info(self, info: str) -> Any:
        return f"info of {info}"


def countdown(*lefts: float) -> Callable[[], float]:
    """A time left that is each of `lefts` in turn."""
    values = iter(lefts)
    return lambda: next(values)


@pytest.fixture
def fake() -> FakeStream:
    return FakeStream()


@pytest.fixture
def stream(fake: FakeStream) -> DeadlineNetworkStream:
    return DeadlineNetworkStream(fake)


class TestTheNetworkStream:
    def test_keeps_httpxs_timeouts_outside_an_attempt(
        self, fake: FakeStream, stream: DeadlineNetworkStream
    ) -> None:
        assert stream.read(10, 5) == b"data"
        stream.write(b"abc", 5)
        stream.read(10)
        assert fake.calls == [("read", 10, 5), ("write", 3, 5), ("read", 10, None)]

    def test_cuts_each_timeout_to_the_time_left(
        self, fake: FakeStream, stream: DeadlineNetworkStream
    ) -> None:
        with attempt_deadline(countdown(2, 2, 0.5, 4)):
            stream.read(10, 5)
            stream.read(10, None)
            stream.write(b"abc", 5)
            stream.read(10, 1)
        assert fake.calls == [("read", 10, 2), ("read", 10, 2), ("write", 3, 0.5), ("read", 10, 1)]

    @pytest.mark.parametrize("left", [0, -1])
    def test_refuses_every_operation_once_the_time_is_up(
        self, fake: FakeStream, stream: DeadlineNetworkStream, left: float
    ) -> None:
        context = ssl.create_default_context()
        with attempt_deadline(lambda: left):
            with pytest.raises(httpcore.ReadTimeout, match="deadline passed"):
                stream.read(10, 5)
            with pytest.raises(httpcore.WriteTimeout):
                stream.write(b"abc", 5)
            with pytest.raises(httpcore.ConnectTimeout):
                stream.start_tls(context, "api.flashpi.com.ec", 5)
        assert fake.calls == []

    def test_writes_in_pieces_each_limited_to_the_time_left_when_it_starts(
        self, fake: FakeStream, stream: DeadlineNetworkStream
    ) -> None:
        size = 2 * WRITE_PIECE + 100
        with attempt_deadline(countdown(3, 2, 1)):
            stream.write(bytes(size), 5)
            stream.write(b"", 5)
        assert fake.calls == [
            ("write", WRITE_PIECE, 3),
            ("write", WRITE_PIECE, 2),
            ("write", 100, 1),
        ]

    def test_keeps_the_deadline_after_the_tls_handshake(
        self, fake: FakeStream, stream: DeadlineNetworkStream
    ) -> None:
        with attempt_deadline(countdown(2, 1)):
            secure = stream.start_tls(ssl.create_default_context(), "api.flashpi.com.ec", 5)
            assert isinstance(secure, DeadlineNetworkStream)
            secure.read(10, 5)
        assert fake.calls == [("start_tls", "api.flashpi.com.ec", 2)]

    def test_passes_close_and_extra_info_through(
        self, fake: FakeStream, stream: DeadlineNetworkStream
    ) -> None:
        assert stream.get_extra_info("is_readable") == "info of is_readable"
        stream.close()
        assert fake.calls == [("close",)]


class TestTheBackend:
    @pytest.fixture
    def server(self) -> Iterator[LocalServer]:
        with LocalServer(answer_at_once) as server:
            yield server

    def test_connects_within_the_time_left(self, server: LocalServer) -> None:
        port = int(server.url.rsplit(":", 1)[1])
        with attempt_deadline(lambda: 5):
            stream = DeadlineBackend().connect_tcp("127.0.0.1", port, timeout=10)
        assert isinstance(stream, DeadlineNetworkStream)
        stream.close()

    def test_does_not_connect_once_the_time_is_up(self, server: LocalServer) -> None:
        port = int(server.url.rsplit(":", 1)[1])
        with (
            attempt_deadline(lambda: 0),
            pytest.raises(httpcore.ConnectTimeout, match="deadline passed"),
        ):
            DeadlineBackend().connect_tcp("127.0.0.1", port, timeout=10)
        time.sleep(0.1)
        assert server.connections == 0
