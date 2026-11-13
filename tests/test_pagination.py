"""Lists and pagination (Node: test/pagination.test.ts)."""

import httpx
import pytest

from flashpi import AsyncPaginator, FlashpiError
from tests.conftest import MakeApi
from tests.support import AsyncTestClient, SyncTestClient, json_response, page

pytestmark = pytest.mark.anyio


async def test_awaits_to_the_first_page(make: MakeApi) -> None:
    api = make(page([{"id": "a"}, {"id": "b"}], "cursor-1"))
    first = await api.call("list", {"status": "authorized", "limit": 2, "issuerId": None})
    assert type(first).__name__ == ("Page" if api.kind == "sync" else "AsyncPage")
    assert first.data == [{"id": "a"}, {"id": "b"}]
    assert first.has_more is True
    assert first.next_cursor == "cursor-1"
    assert first.has_next_page()
    assert api.sent[0].url.query == b"status=authorized&limit=2"
    assert repr(first).endswith("(data=<2 items>, has_more=True, next_cursor='cursor-1')")


async def test_fetches_the_next_page_with_the_same_filters_and_options(make: MakeApi) -> None:
    api = make(page([{"id": "a"}], "c1"), page([{"id": "b"}]))
    first = await api.call("list", {"type": "invoice"}, language="es")
    second = await api.next_page(first)
    assert second.data == [{"id": "b"}]
    assert not second.has_next_page()
    assert await api.next_page(second) is None
    assert api.sent[1].url.query == b"type=invoice&cursor=c1"
    assert api.sent[1].headers["accept-language"] == "es"


async def test_iterates_every_item_across_pages(make: MakeApi) -> None:
    api = make(
        page([{"id": "a"}, {"id": "b"}], "c1"),
        page([], "c2"),
        page([{"id": "c"}]),
    )
    items = await api.collect({"limit": 2})
    assert [item["id"] for item in items] == ["a", "b", "c"]
    assert [request.url.query for request in api.sent] == [
        b"limit=2",
        b"limit=2&cursor=c1",
        b"limit=2&cursor=c2",
    ]


async def test_iterates_from_an_awaited_page_too(make: MakeApi) -> None:
    api = make(page([{"id": "a"}], "c1"), page([{"id": "b"}]))
    first = await api.call("list")
    assert [item["id"] for item in await api.iterate(first)] == ["a", "b"]


async def test_starts_from_a_given_cursor(make: MakeApi) -> None:
    api = make(page([]))
    await api.call("list", {"cursor": "from-here", "limit": 100, "archived": False})
    assert api.sent[0].url.query == b"cursor=from-here&limit=100&archived=false"


async def test_encodes_query_values(make: MakeApi) -> None:
    api = make(page([]))
    await api.call("list", {"q": "a b&c=d/é+", "flag": True})
    assert api.sent[0].url.query == b"q=a+b%26c%3Dd%2F%C3%A9%2B&flag=true"


async def test_does_not_follow_a_page_that_says_has_more_without_a_cursor(make: MakeApi) -> None:
    api = make(json_response({"data": [], "pagination": {"hasMore": True, "nextCursor": None}}))
    first = await api.call("list")
    assert not first.has_next_page()
    assert await api.next_page(first) is None
    assert await api.iterate(first) == []


async def test_exposes_the_response_of_the_first_page(make: MakeApi) -> None:
    api = make(page([]))
    result = await api.call_with_response("list")
    assert result.data.data == []
    assert result.request_id == "req_123"


async def test_refuses_a_list_answer_without_data_and_pagination(make: MakeApi) -> None:
    api = make(json_response({"data": []}), json_response([1, 2]))
    with pytest.raises(FlashpiError, match="without data and pagination"):
        await api.call("list")
    with pytest.raises(FlashpiError, match="without data and pagination"):
        await api.call("list")


def test_stops_when_the_caller_breaks_out_of_the_loop() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return page([{"id": "a"}, {"id": "b"}], "c1")

    client = SyncTestClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    for item in client.things.list():
        assert item["id"] == "a"
        break
    assert len(sent) == 1


async def test_stops_an_async_walk_when_the_caller_breaks_out_of_the_loop() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return page([{"id": "a"}, {"id": "b"}], "c1")

    transport = httpx.MockTransport(handler)
    client = AsyncTestClient(http_client=httpx.AsyncClient(transport=transport))
    paginator = client.things.list()
    assert isinstance(paginator, AsyncPaginator)
    assert sent == []
    async for item in paginator:
        assert item["id"] == "a"
        break
    assert len(sent) == 1
    # The first page is fetched once, however often the paginator is awaited.
    assert (await paginator).data == [{"id": "a"}, {"id": "b"}]
    assert len(sent) == 1
