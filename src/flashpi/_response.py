"""The data of a call together with the HTTP response it came from (Node's `withResponse()`).

Resources expose it through a `with_response` view whose methods are wrapped with
`response_wrapper` (sync) or `async_response_wrapper` (async): the wrapped call records the last
successful response in a context variable, so the methods themselves stay unchanged.
"""

import functools
from collections.abc import Awaitable, Callable, Coroutine
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Generic, ParamSpec, TypeVar

import httpx

from ._errors import FlashpiError

T = TypeVar("T")
P = ParamSpec("P")


@dataclass(frozen=True)
class APIResponse(Generic[T]):
    """The data of a call, the HTTP response it came from and Flashpi's request id."""

    data: T
    """What the method returns."""

    response: httpx.Response
    """The HTTP response (status, headers). Its body was already read into `data`."""

    request_id: str | None
    """Flashpi's id of the request (`x-request-id`): share it with support."""


class _Capture:
    __slots__ = ("result",)

    def __init__(self) -> None:
        self.result: APIResponse[Any] | None = None


_capture: ContextVar[_Capture | None] = ContextVar("flashpi_response_capture", default=None)


def record_response(result: APIResponse[Any]) -> None:
    """Keeps `result` for the `with_response` call running in this context, if any."""
    capture = _capture.get()
    if capture is not None:
        capture.result = result


def _finish(capture: _Capture, data: T) -> APIResponse[T]:
    if capture.result is None:
        raise FlashpiError("The call sent no request, so there is no response to return")
    return APIResponse(
        data=data, response=capture.result.response, request_id=capture.result.request_id
    )


def response_wrapper(method: Callable[P, T]) -> Callable[P, APIResponse[T]]:
    """`method` returning an `APIResponse` around its data."""

    @functools.wraps(method)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> APIResponse[T]:
        capture = _Capture()
        token = _capture.set(capture)
        try:
            data = method(*args, **kwargs)
        finally:
            _capture.reset(token)
        return _finish(capture, data)

    return wrapped


def async_response_wrapper(
    method: Callable[P, Awaitable[T]],
) -> Callable[P, Coroutine[Any, Any, APIResponse[T]]]:
    """The async `method` returning an `APIResponse` around its data: a coroutine, so it can run
    as a task (`asyncio.create_task`, `TaskGroup.create_task`)."""

    @functools.wraps(method)
    async def wrapped(*args: P.args, **kwargs: P.kwargs) -> APIResponse[T]:
        capture = _Capture()
        token = _capture.set(capture)
        try:
            data = await method(*args, **kwargs)
        finally:
            _capture.reset(token)
        return _finish(capture, data)

    return wrapped
