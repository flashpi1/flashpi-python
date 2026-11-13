"""Base of every resource: resources only declare their operations as `RequestSpec`s.

```python
class Documents(SyncAPIResource):
    def get(self, document_id: str, **options: Unpack[RequestOptions]) -> Document:
        return self._request(
            RequestSpec[Document](
                method="GET", path=path_of("/v1/documents/{}", document_id), options=options
            )
        )

    def list(
        self, params: DocumentListParams | None = None, **options: Unpack[RequestOptions]
    ) -> Page[Document]:
        return self._list(
            RequestSpec[ListBody[Document]](
                method="GET", path="/v1/documents", query=params, options=options
            )
        )
```
"""

from dataclasses import replace
from typing import TypeVar

from ._http import AsyncEngine, RequestSpec, SyncEngine
from ._pagination import AsyncPage, AsyncPaginator, ListBody, Page
from ._response import APIResponse, record_response

T = TypeVar("T")


def _with_cursor(spec: RequestSpec[ListBody[T]], cursor: str) -> RequestSpec[ListBody[T]]:
    """The same list request for the page after `cursor` (same filters and options)."""
    return replace(spec, query={**(spec.query or {}), "cursor": cursor})


class SyncAPIResource:
    """Base of the resources of `Flashpi`."""

    def __init__(self, engine: SyncEngine) -> None:
        self._engine = engine

    def _call(self, spec: RequestSpec[T]) -> APIResponse[T]:
        """Sends the request (with its retries) and returns its data with the response."""
        result = self._engine.request(spec)
        record_response(result)
        return result

    def _request(self, spec: RequestSpec[T]) -> T:
        """Sends the request (with its retries) and returns its data."""
        return self._call(spec).data

    def _list(self, spec: RequestSpec[ListBody[T]]) -> Page[T]:
        """The first page of a list; iterating it walks every page."""

        def fetch(page_spec: RequestSpec[ListBody[T]]) -> APIResponse[Page[T]]:
            result = self._engine.request(page_spec)
            page = Page(result.data, lambda cursor: fetch(_with_cursor(spec, cursor)).data)
            return APIResponse(data=page, response=result.response, request_id=result.request_id)

        first = fetch(spec)
        record_response(first)
        return first.data


class AsyncAPIResource:
    """Base of the resources of `AsyncFlashpi`."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _call(self, spec: RequestSpec[T]) -> APIResponse[T]:
        """Sends the request (with its retries) and returns its data with the response."""
        result = await self._engine.request(spec)
        record_response(result)
        return result

    async def _request(self, spec: RequestSpec[T]) -> T:
        """Sends the request (with its retries) and returns its data."""
        return (await self._call(spec)).data

    def _list(self, spec: RequestSpec[ListBody[T]]) -> AsyncPaginator[T]:
        """Awaitable for the first page; `async for` walks every item across pages."""

        async def fetch(page_spec: RequestSpec[ListBody[T]]) -> APIResponse[AsyncPage[T]]:
            result = await self._engine.request(page_spec)

            async def next_page(cursor: str) -> AsyncPage[T]:
                return (await fetch(_with_cursor(spec, cursor))).data

            page = AsyncPage(result.data, next_page)
            return APIResponse(data=page, response=result.response, request_id=result.request_id)

        async def first_page() -> AsyncPage[T]:
            first = await fetch(spec)
            record_response(first)
            return first.data

        return AsyncPaginator(first_page)
