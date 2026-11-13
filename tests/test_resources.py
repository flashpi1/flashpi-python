"""Every resource method sends its operation (Node: test/resources.test.ts)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from flashpi import APIResponse
from tests.conftest import MakeApi
from tests.support import json_response, page, sent_json

pytestmark = pytest.mark.anyio

ISSUER = "iss_1"
ESTABLISHMENT = "est_1"
POINT = "pt_1"
CERTIFICATE = "cert_1"
ONBOARDING = "onb_1"
DOCUMENT = "doc_1"
ENDPOINT = "whe_1"
DELIVERY = "del_1"
EVENT = "evt_1"

NO_BODY: Any = object()


def no_content() -> httpx.Response:
    return httpx.Response(204)


def empty_page() -> httpx.Response:
    return page([])


def empty_object() -> httpx.Response:
    return json_response({})


@dataclass(frozen=True)
class Case:
    """A resource method, what it is called with and the request it must send."""

    name: str
    args: tuple[Any, ...]
    method: str
    path: str
    body: Any = NO_BODY
    query: Mapping[str, str] = field(default_factory=dict[str, str])
    reply: Callable[[], httpx.Response] = empty_object
    label: str = ""


CASES = [
    Case("status.get", (), "GET", "/v1/status"),
    Case(
        "events.list",
        ({"documentId": DOCUMENT},),
        "GET",
        "/v1/events",
        query={"documentId": DOCUMENT},
        reply=empty_page,
    ),
    Case("events.get", (EVENT,), "GET", f"/v1/events/{EVENT}"),
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.label or case.name)
async def test_sends_its_operation(make: MakeApi, case: Case) -> None:
    api = make(case.reply())
    await api.op(case.name, *case.args)
    assert len(api.sent) == 1
    request = api.sent[0]
    assert request.method == case.method
    assert request.url.path == case.path
    assert dict(request.url.params) == case.query
    if case.body is NO_BODY:
        assert request.content == b""
        assert "content-type" not in request.headers
    else:
        assert sent_json(request) == case.body
        assert request.headers["content-type"] == "application/json"
    assert ("idempotency-key" in request.headers) == (case.method == "POST")


async def test_returns_the_api_status(make: MakeApi) -> None:
    api = make(json_response({"status": "operational"}))
    assert await api.op("status.get") == {"status": "operational"}


async def test_walks_every_event_across_pages_with_the_same_filters(make: MakeApi) -> None:
    api = make(page([{"id": "evt_1"}], "c1"), page([{"id": "evt_2"}]))
    first = await api.op("events.list", {"documentId": DOCUMENT, "limit": 1})
    assert [event["id"] for event in await api.iterate(first)] == ["evt_1", "evt_2"]
    assert [dict(request.url.params) for request in api.sent] == [
        {"documentId": DOCUMENT, "limit": "1"},
        {"documentId": DOCUMENT, "limit": "1", "cursor": "c1"},
    ]


@pytest.mark.parametrize(("name", "args"), [("status.get", ()), ("events.get", (EVENT,))])
async def test_returns_the_response_with_with_response(
    make: MakeApi, name: str, args: tuple[str, ...]
) -> None:
    api = make(json_response({"id": EVENT}, 200, {"x-request-id": "req_event"}))
    result = await api.op_with_response(name, *args)
    assert isinstance(result, APIResponse)
    assert result.data == {"id": EVENT}
    assert result.request_id == "req_event"
    assert result.response.status_code == 200
