"""The deadline of a `Flashpi` attempt, down to each network operation.

httpx gives each operation of a sync request (connecting, the TLS handshake, each write, each
read) a timeout of its own, so an answer whose headers trickle in could keep an attempt going for
as long as they trickle. `AsyncFlashpi` has `asyncio.timeout()`. For `Flashpi`, the httpx client
the SDK creates gets a network backend that limits every operation to the time its attempt has
left, as the Node SDK's AbortController does. It reaches httpcore, which httpx always installs,
through private attributes of both (pinned by tests); a pool it does not recognize keeps httpx's
own limits, and so does a caller's `http_client`.
"""

import ssl
from collections.abc import Callable, Generator, Iterable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, cast

import httpcore
import httpx

WRITE_PIECE = 16_384
"""httpcore sends a buffer in a loop whose every send() gets the whole timeout: written in pieces
of this size, each piece gets the time left when it starts."""

_time_left: ContextVar[Callable[[], float] | None] = ContextVar("flashpi_time_left", default=None)


@contextmanager
def attempt_deadline(time_left: Callable[[], float]) -> Generator[None, None, None]:
    """Limits the network operations of this thread (or task) to `time_left()` seconds."""
    token = _time_left.set(time_left)
    try:
        yield
    finally:
        _time_left.reset(token)


def limit_to_attempt_deadlines(client: httpx.Client) -> None:
    """Gives every connection pool of a client the SDK created, its own and those of the proxies
    from the environment, the backend that keeps the attempts' deadlines.

    Fail-safe: a version of httpx or httpcore without these private attributes leaves the client
    as httpx built it, with httpx's own limits (the deadline is then checked only while the body
    arrives and once it is read), and nothing breaks. tests/test_network.py fails in CI when that
    happens, so the change is seen before a release."""
    transports: list[object] = [getattr(client, "_transport", None)]
    mounts: object = getattr(client, "_mounts", None)
    if isinstance(mounts, Mapping):
        transports.extend(cast("Mapping[object, object]", mounts).values())
    for transport in transports:
        pool: object = getattr(transport, "_pool", None)
        if isinstance(pool, httpcore.ConnectionPool) and hasattr(pool, "_network_backend"):
            pool._network_backend = DeadlineBackend()  # pyright: ignore[reportPrivateUsage]


def limited(timeout: float | None, error: type[httpcore.TimeoutException]) -> float | None:
    """`timeout`, cut to the time the attempt has left; `error` once it has none."""
    time_left = _time_left.get()
    if time_left is None:
        return timeout
    left = time_left()
    if left <= 0:
        raise error("The attempt's deadline passed")
    return left if timeout is None else min(timeout, left)


class DeadlineBackend(httpcore.SyncBackend):
    """httpcore's sync backend, with every operation limited to the time its attempt has left."""

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        stream = super().connect_tcp(
            host, port, limited(timeout, httpcore.ConnectTimeout), local_address, socket_options
        )
        return DeadlineNetworkStream(stream)


class DeadlineNetworkStream(httpcore.NetworkStream):
    """A connection whose reads, writes and TLS handshake keep the attempt's deadline."""

    def __init__(self, stream: httpcore.NetworkStream) -> None:
        self._stream = stream

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(max_bytes, limited(timeout, httpcore.ReadTimeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        for start in range(0, len(buffer), WRITE_PIECE):
            piece = buffer[start : start + WRITE_PIECE]
            self._stream.write(piece, limited(timeout, httpcore.WriteTimeout))

    def close(self) -> None:
        self._stream.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        stream = self._stream.start_tls(
            ssl_context, server_hostname, limited(timeout, httpcore.ConnectTimeout)
        )
        return DeadlineNetworkStream(stream)

    def get_extra_info(self, info: str) -> Any:  # noqa: ANN401 (httpcore's own signature)
        # The pool asks for "is_readable" before it reuses a connection.
        return self._stream.get_extra_info(info)
