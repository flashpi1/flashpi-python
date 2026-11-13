"""Test helpers: a mocked API on httpx.MockTransport, a fake clock, and a harness that runs each
operation on the sync or the async client, so every behavior test covers both."""

import asyncio
import inspect
import json
from collections.abc import Awaitable, Callable, Iterable, Mapping
from functools import cached_property
from typing import Any, Literal, TypeAlias, Unpack, cast

import httpx

from flashpi import AsyncFlashpi, Flashpi, Page, RequestOptions
from flashpi._http import Multipart, RequestSpec, path_of
from flashpi._pagination import AsyncPage, AsyncPaginator, ListBody
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import APIResponse, async_response_wrapper, response_wrapper

TEST_KEY = f"fp_test_{'a' * 16}{'b' * 32}"
LIVE_KEY = f"fp_live_{'a' * 16}{'b' * 32}"
ID = "019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6a7b"
OTHER_ID = "019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6a7c"

Kind: TypeAlias = Literal["sync", "async"]
Handler: TypeAlias = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]
Reply: TypeAlias = httpx.Response | BaseException | Handler
Thing: TypeAlias = dict[str, Any]


class MockAPI:
    """Answers from a queue and records what it received. An exception in the queue is raised
    like a network failure; a function answers dynamically (and may be async)."""

    def __init__(self, replies: Iterable[Reply]) -> None:
        self.sent: list[httpx.Request] = []
        self._queue = list(replies)

    def handler(self, request: httpx.Request) -> httpx.Response | Awaitable[httpx.Response]:
        self.sent.append(request)
        if not self._queue:
            raise AssertionError(f"Unexpected request {request.method} {request.url}")
        reply = self._queue.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        if isinstance(reply, httpx.Response):
            return reply
        return reply(request)


def json_response(
    body: object, status: int = 200, headers: Mapping[str, str] | None = None
) -> httpx.Response:
    """A JSON answer."""
    return httpx.Response(
        status,
        content=json.dumps(body).encode(),
        headers={"content-type": "application/json", "x-request-id": "req_123", **(headers or {})},
    )


def problem(
    status: int,
    code: str,
    extra: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    """A Problem Details answer like the API's."""
    body: dict[str, object] = {
        "type": f"https://flashpi.com.ec/docs/en/errors/{code}",
        "title": "Problem",
        "status": status,
        "detail": f"Detail of {code}",
        "instance": "/v1/test",
        "code": code,
        "errors": [],
        "requestId": "req_problem",
        **(extra or {}),
    }
    return httpx.Response(
        status,
        content=json.dumps(body).encode(),
        headers={
            "content-type": "application/problem+json; charset=utf-8",
            "x-request-id": "req_problem",
            **(headers or {}),
        },
    )


def page(data: list[Thing], next_cursor: str | None = None) -> httpx.Response:
    """A list answer."""
    return json_response(
        {
            "data": data,
            "pagination": {"nextCursor": next_cursor, "hasMore": next_cursor is not None},
        }
    )


def document_body(document_id: str = ID, status: str = "processing") -> Thing:
    """A minimal document as the API returns it (only the members the tests read)."""
    return {
        "id": document_id,
        "type": "invoice",
        "status": status,
        "environment": "test",
        "accessKey": "1" * 49,
    }


def sent_json(request: httpx.Request) -> Any:
    """The JSON body a request sent."""
    return json.loads(request.content)


class Clock:
    """A fake clock: sleeping advances it at once."""

    def __init__(self) -> None:
        self.now = 1_000.0
        self.started = self.now
        self.sleeps: list[float] = []

    @property
    def elapsed(self) -> float:
        return round(self.now - self.started, 3)

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.advance(seconds)

    async def async_sleep(self, seconds: float) -> None:
        self.sleep(seconds)
        await asyncio.sleep(0)


def timeout_after(clock: Clock, seconds: float) -> Handler:
    """A reply that takes `seconds` and then times out, like a request the API never answers."""

    def reply(request: httpx.Request) -> httpx.Response:
        clock.advance(seconds)
        raise httpx.ReadTimeout("timed out", request=request)

    return reply


# Test resources, declared as the real resources declare their operations.


def issue_spec(body: Thing, options: RequestOptions) -> RequestSpec[Thing]:
    """A document POST, like the Node SDK's DocumentIssuer.create()."""
    document_options: Thing = body.get("options") or {}
    sync = document_options.get("waitForAuthorization") is True
    wait_seconds: float = document_options.get("waitTimeoutSeconds", 15)
    return RequestSpec[Thing](
        method="POST",
        path="/v1/invoices",
        body=body,
        options=options,
        min_timeout=wait_seconds + 15 if sync else 0,
        recover_document=True,
    )


def upload_spec(content: bytes, password: str, options: RequestOptions) -> RequestSpec[Thing]:
    return RequestSpec[Thing](
        method="POST",
        path="/v1/uploads",
        multipart=Multipart(
            fields={"password": password},
            files={"file": ("certificate.p12", content, "application/x-pkcs12")},
        ),
        options=options,
    )


class SyncThings(SyncAPIResource):
    def status(self, **options: Unpack[RequestOptions]) -> Thing:
        return self._request(RequestSpec[Thing](method="GET", path="/v1/status", options=options))

    def get(self, thing_id: str, **options: Unpack[RequestOptions]) -> Thing:
        path = path_of("/v1/things/{}", thing_id)
        return self._request(RequestSpec[Thing](method="GET", path=path, options=options))

    def get_nested(self, first: str, second: str, **options: Unpack[RequestOptions]) -> Thing:
        path = path_of("/v1/things/{}/parts/{}", first, second)
        return self._request(RequestSpec[Thing](method="GET", path=path, options=options))

    def create(self, body: Thing | None, **options: Unpack[RequestOptions]) -> Thing:
        spec = RequestSpec[Thing](method="POST", path="/v1/things", body=body, options=options)
        return self._request(spec)

    def issue(self, body: Thing, **options: Unpack[RequestOptions]) -> Thing:
        return self._request(issue_spec(body, options))

    def update(self, thing_id: str, body: Thing, **options: Unpack[RequestOptions]) -> Thing:
        path = path_of("/v1/things/{}", thing_id)
        spec = RequestSpec[Thing](method="PATCH", path=path, body=body, options=options)
        return self._request(spec)

    def delete(self, thing_id: str, **options: Unpack[RequestOptions]) -> None:
        path = path_of("/v1/things/{}", thing_id)
        spec = RequestSpec[None](method="DELETE", path=path, response_type="none", options=options)
        return self._request(spec)

    def list(self, query: Thing | None = None, **options: Unpack[RequestOptions]) -> Page[Thing]:
        spec = RequestSpec[ListBody[Thing]](
            method="GET", path="/v1/things", query=query, options=options
        )
        return self._list(spec)

    def text(self, thing_id: str, **options: Unpack[RequestOptions]) -> str:
        path = path_of("/v1/things/{}/xml", thing_id)
        accept = "application/xml, application/problem+json"
        spec = RequestSpec[str](
            method="GET", path=path, accept=accept, response_type="text", options=options
        )
        return self._request(spec)

    def raw(self, thing_id: str, **options: Unpack[RequestOptions]) -> bytes:
        path = path_of("/v1/things/{}/pdf", thing_id)
        accept = "application/pdf, application/problem+json"
        spec = RequestSpec[bytes](
            method="GET", path=path, accept=accept, response_type="bytes", options=options
        )
        return self._request(spec)

    def upload(self, content: bytes, password: str, **options: Unpack[RequestOptions]) -> Thing:
        return self._request(upload_spec(content, password, options))

    @cached_property
    def with_response(self) -> "SyncThingsWithResponse":
        return SyncThingsWithResponse(self)


class SyncThingsWithResponse:
    def __init__(self, things: SyncThings) -> None:
        self.get = response_wrapper(things.get)
        self.issue = response_wrapper(things.issue)
        self.delete = response_wrapper(things.delete)
        self.list = response_wrapper(things.list)


class AsyncThings(AsyncAPIResource):
    async def status(self, **options: Unpack[RequestOptions]) -> Thing:
        return await self._request(
            RequestSpec[Thing](method="GET", path="/v1/status", options=options)
        )

    async def get(self, thing_id: str, **options: Unpack[RequestOptions]) -> Thing:
        path = path_of("/v1/things/{}", thing_id)
        return await self._request(RequestSpec[Thing](method="GET", path=path, options=options))

    async def get_nested(self, first: str, second: str, **options: Unpack[RequestOptions]) -> Thing:
        path = path_of("/v1/things/{}/parts/{}", first, second)
        return await self._request(RequestSpec[Thing](method="GET", path=path, options=options))

    async def create(self, body: Thing | None, **options: Unpack[RequestOptions]) -> Thing:
        spec = RequestSpec[Thing](method="POST", path="/v1/things", body=body, options=options)
        return await self._request(spec)

    async def issue(self, body: Thing, **options: Unpack[RequestOptions]) -> Thing:
        return await self._request(issue_spec(body, options))

    async def update(self, thing_id: str, body: Thing, **options: Unpack[RequestOptions]) -> Thing:
        path = path_of("/v1/things/{}", thing_id)
        spec = RequestSpec[Thing](method="PATCH", path=path, body=body, options=options)
        return await self._request(spec)

    async def delete(self, thing_id: str, **options: Unpack[RequestOptions]) -> None:
        path = path_of("/v1/things/{}", thing_id)
        spec = RequestSpec[None](method="DELETE", path=path, response_type="none", options=options)
        return await self._request(spec)

    def list(
        self, query: Thing | None = None, **options: Unpack[RequestOptions]
    ) -> AsyncPaginator[Thing]:
        spec = RequestSpec[ListBody[Thing]](
            method="GET", path="/v1/things", query=query, options=options
        )
        return self._list(spec)

    async def text(self, thing_id: str, **options: Unpack[RequestOptions]) -> str:
        path = path_of("/v1/things/{}/xml", thing_id)
        accept = "application/xml, application/problem+json"
        spec = RequestSpec[str](
            method="GET", path=path, accept=accept, response_type="text", options=options
        )
        return await self._request(spec)

    async def raw(self, thing_id: str, **options: Unpack[RequestOptions]) -> bytes:
        path = path_of("/v1/things/{}/pdf", thing_id)
        accept = "application/pdf, application/problem+json"
        spec = RequestSpec[bytes](
            method="GET", path=path, accept=accept, response_type="bytes", options=options
        )
        return await self._request(spec)

    async def upload(
        self, content: bytes, password: str, **options: Unpack[RequestOptions]
    ) -> Thing:
        return await self._request(upload_spec(content, password, options))

    @cached_property
    def with_response(self) -> "AsyncThingsWithResponse":
        return AsyncThingsWithResponse(self)


class AsyncThingsWithResponse:
    def __init__(self, things: AsyncThings) -> None:
        self.get = async_response_wrapper(things.get)
        self.issue = async_response_wrapper(things.issue)
        self.delete = async_response_wrapper(things.delete)
        self.list = async_response_wrapper(things.list)


class SyncTestClient(Flashpi):
    """A Flashpi client with the test resource, as part of the SDK would add a real one."""

    def __init__(self, api_key: str | None = TEST_KEY, **options: Any) -> None:
        super().__init__(api_key, **options)
        self.things = SyncThings(self._engine)


class AsyncTestClient(AsyncFlashpi):
    """An AsyncFlashpi client with the test resource."""

    def __init__(self, api_key: str | None = TEST_KEY, **options: Any) -> None:
        super().__init__(api_key, **options)
        self.things = AsyncThings(self._engine)


class Api:
    """A sync or async test client on a mocked API, behind async methods: each test runs once
    per kind of client."""

    def __init__(self, kind: Kind, replies: Iterable[Reply], **client_options: Any) -> None:
        self.kind = kind
        self.mock = MockAPI(replies)
        # MockTransport awaits what the handler returns when it is awaitable (async replies).
        transport = httpx.MockTransport(cast("Any", self.mock.handler))
        self.sync: SyncTestClient | None = None
        self.async_: AsyncTestClient | None = None
        if kind == "sync":
            http_client = httpx.Client(transport=transport)
            self.sync = SyncTestClient(http_client=http_client, **client_options)
        else:
            async_http_client = httpx.AsyncClient(transport=transport)
            self.async_ = AsyncTestClient(http_client=async_http_client, **client_options)

    @property
    def sent(self) -> list[httpx.Request]:
        return self.mock.sent

    async def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Calls `client.things.<name>(...)`, awaiting it on the async client."""
        if self.sync is not None:
            return getattr(self.sync.things, name)(*args, **kwargs)
        assert self.async_ is not None
        return await getattr(self.async_.things, name)(*args, **kwargs)

    async def call_with_response(self, name: str, *args: Any, **kwargs: Any) -> APIResponse[Any]:
        """Calls `client.things.with_response.<name>(...)`."""
        if self.sync is not None:
            return getattr(self.sync.things.with_response, name)(*args, **kwargs)
        assert self.async_ is not None
        return await getattr(self.async_.things.with_response, name)(*args, **kwargs)

    @property
    def client(self) -> SyncTestClient | AsyncTestClient:
        client = self.sync or self.async_
        assert client is not None
        return client

    def method(self, name: str) -> Any:
        """A resource method of the client by its dotted name (`issuers.certificates.get`)."""
        target: Any = self.client
        for attribute in name.split("."):
            target = getattr(target, attribute)
        return target

    async def op(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Calls a resource method by its dotted name, awaiting it on the async client (a list
        gives its first page)."""
        result = self.method(name)(*args, **kwargs)
        return await result if inspect.isawaitable(result) else result

    async def op_with_response(self, name: str, *args: Any, **kwargs: Any) -> APIResponse[Any]:
        """Calls the `with_response` view of a resource method: `op_with_response("documents.xml",
        ...)` calls `client.documents.with_response.xml(...)`."""
        resource, _, method = name.rpartition(".")
        return await self.op(f"{resource}.with_response.{method}", *args, **kwargs)

    async def collect(self, query: Thing | None = None, **options: Any) -> list[Thing]:
        """Every item of a list, across pages."""
        if self.sync is not None:
            return list(self.sync.things.list(query, **options))
        assert self.async_ is not None
        return [item async for item in self.async_.things.list(query, **options)]

    async def next_page(self, current: Page[Thing] | AsyncPage[Thing]) -> Any:
        if isinstance(current, Page):
            return current.next_page()
        return await current.next_page()

    async def iterate(self, current: Page[Thing] | AsyncPage[Thing]) -> list[Thing]:
        """Every item of a page and the following ones."""
        if isinstance(current, Page):
            return list(current)
        return [item async for item in current]
