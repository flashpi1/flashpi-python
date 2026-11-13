"""Pages of a list, and the iteration over every page."""

from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Iterator
from typing import Any, Generic, TypedDict, TypeVar, cast

from ._errors import FlashpiError
from .types import Pagination

T = TypeVar("T")


class ListBody(TypedDict, Generic[T]):
    """The body of every list operation of the API."""

    data: list[T]
    pagination: Pagination


class _BasePage(Generic[T]):
    data: list[T]
    """The items of this page."""

    has_more: bool
    """Whether more items follow this page."""

    next_cursor: str | None
    """The cursor of the next page, or None on the last one."""

    def __init__(self, body: ListBody[T]) -> None:
        members = cast("object", body)
        data = pagination = None
        if isinstance(members, dict):
            data = cast("dict[str, object]", members).get("data")
            pagination = cast("dict[str, object]", members).get("pagination")
        if not isinstance(data, list) or not isinstance(pagination, dict):
            raise FlashpiError("The API answered a list without data and pagination")
        cursor = cast("dict[str, object]", pagination).get("nextCursor")
        self.data = cast("list[T]", data)
        self.has_more = cast("dict[str, object]", pagination).get("hasMore") is True
        self.next_cursor = cursor if isinstance(cursor, str) else None

    def has_next_page(self) -> bool:
        """Whether `next_page()` will return a page."""
        return self.has_more and self.next_cursor is not None

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(data=<{len(self.data)} items>, has_more={self.has_more}, "
            f"next_cursor={self.next_cursor!r})"
        )


class Page(_BasePage[T]):
    """One page of a list, newest first (establishments and emission points: by code).

    Iterate it with `for` to walk this page and every following one, fetching them as needed:

    ```python
    for document in flashpi.documents.list(status="authorized"):
        print(document["accessKey"])
    ```
    """

    def __init__(self, body: ListBody[T], fetch_page: Callable[[str], "Page[T]"]) -> None:
        super().__init__(body)
        self._fetch_page = fetch_page

    def next_page(self) -> "Page[T] | None":
        """The next page (same filters and options), or None after the last page."""
        if not self.has_next_page() or self.next_cursor is None:
            return None
        return self._fetch_page(self.next_cursor)

    def __iter__(self) -> Iterator[T]:
        page: Page[T] | None = self
        while page is not None:
            yield from page.data
            page = page.next_page()


class AsyncPage(_BasePage[T]):
    """One page of a list, for `AsyncFlashpi`. Iterate it with `async for` to walk this page and
    every following one, fetching them as needed."""

    def __init__(
        self, body: ListBody[T], fetch_page: Callable[[str], Awaitable["AsyncPage[T]"]]
    ) -> None:
        super().__init__(body)
        self._fetch_page = fetch_page

    async def next_page(self) -> "AsyncPage[T] | None":
        """The next page (same filters and options), or None after the last page."""
        if not self.has_next_page() or self.next_cursor is None:
            return None
        return await self._fetch_page(self.next_cursor)

    async def __aiter__(self) -> AsyncIterator[T]:
        page: AsyncPage[T] | None = self
        while page is not None:
            for item in page.data:
                yield item
            page = await page.next_page()


class AsyncPaginator(Generic[T]):
    """The result of a list call of `AsyncFlashpi`.

    Await it for the first page, or iterate it with `async for` to walk every item across pages:

    ```python
    async for document in flashpi.documents.list(status="authorized"):
        print(document["accessKey"])
    ```
    """

    def __init__(self, fetch_first_page: Callable[[], Awaitable[AsyncPage[T]]]) -> None:
        self._fetch_first_page = fetch_first_page
        self._page: AsyncPage[T] | None = None

    async def _first_page(self) -> AsyncPage[T]:
        if self._page is None:
            self._page = await self._fetch_first_page()
        return self._page

    def __await__(self) -> Generator[Any, None, AsyncPage[T]]:
        return self._first_page().__await__()

    async def __aiter__(self) -> AsyncIterator[T]:
        async for item in await self._first_page():
            yield item
