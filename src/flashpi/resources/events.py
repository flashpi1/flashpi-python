"""Events: what happened to documents, certificates and email sending, newest first."""

from functools import cached_property
from typing import Unpack

from flashpi._http import RequestOptions, RequestSpec, path_of
from flashpi._pagination import AsyncPaginator, ListBody, Page
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import async_response_wrapper, response_wrapper
from flashpi.types import Event, EventListParams


def list_spec(
    params: EventListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[Event]]:
    return RequestSpec[ListBody[Event]](
        method="GET", path="/v1/events", query=params, options=options
    )


def get_spec(event_id: str, options: RequestOptions) -> RequestSpec[Event]:
    path = path_of("/v1/events/{}", event_id)
    return RequestSpec[Event](method="GET", path=path, options=options)


class Events(SyncAPIResource):
    """Events: what happened to documents, certificates and email sending, newest first."""

    def list(
        self, params: EventListParams | None = None, **options: Unpack[RequestOptions]
    ) -> Page[Event]:
        """Lists events, optionally by type, issuer, document or certificate."""
        return self._list(list_spec(params, options))

    def get(self, event_id: str, **options: Unpack[RequestOptions]) -> Event:
        """Retrieves an event: the same object its webhook delivered."""
        return self._request(get_spec(event_id, options))

    @cached_property
    def with_response(self) -> "EventsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return EventsWithResponse(self)


class EventsWithResponse:
    def __init__(self, events: Events) -> None:
        self.list = response_wrapper(events.list)
        self.get = response_wrapper(events.get)


class AsyncEvents(AsyncAPIResource):
    """Events: what happened to documents, certificates and email sending, newest first."""

    def list(
        self, params: EventListParams | None = None, **options: Unpack[RequestOptions]
    ) -> AsyncPaginator[Event]:
        """Lists events, optionally by type, issuer, document or certificate."""
        return self._list(list_spec(params, options))

    async def get(self, event_id: str, **options: Unpack[RequestOptions]) -> Event:
        """Retrieves an event: the same object its webhook delivered."""
        return await self._request(get_spec(event_id, options))

    @cached_property
    def with_response(self) -> "AsyncEventsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncEventsWithResponse(self)


class AsyncEventsWithResponse:
    def __init__(self, events: AsyncEvents) -> None:
        self.list = async_response_wrapper(events.list)
        self.get = async_response_wrapper(events.get)
