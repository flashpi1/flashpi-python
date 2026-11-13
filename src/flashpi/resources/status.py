"""The API's own status. It needs no API key."""

from functools import cached_property
from typing import Unpack

from flashpi._http import RequestOptions, RequestSpec
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import async_response_wrapper, response_wrapper
from flashpi.types import Status


class StatusResource(SyncAPIResource):
    """The API's own status (Node: `Status`, exported as `StatusResource`)."""

    def get(self, **options: Unpack[RequestOptions]) -> Status:
        """Whether Flashpi is operational."""
        return self._request(RequestSpec[Status](method="GET", path="/v1/status", options=options))

    @cached_property
    def with_response(self) -> "StatusResourceWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return StatusResourceWithResponse(self)


class StatusResourceWithResponse:
    def __init__(self, status: StatusResource) -> None:
        self.get = response_wrapper(status.get)


class AsyncStatusResource(AsyncAPIResource):
    """The API's own status, for `AsyncFlashpi`."""

    async def get(self, **options: Unpack[RequestOptions]) -> Status:
        """Whether Flashpi is operational."""
        return await self._request(
            RequestSpec[Status](method="GET", path="/v1/status", options=options)
        )

    @cached_property
    def with_response(self) -> "AsyncStatusResourceWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncStatusResourceWithResponse(self)


class AsyncStatusResourceWithResponse:
    def __init__(self, status: AsyncStatusResource) -> None:
        self.get = async_response_wrapper(status.get)
