"""Every resource method sends its operation (Node: test/resources.test.ts)."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from flashpi import APIResponse, APITimeoutError, ConflictError
from tests.conftest import MakeApi
from tests.support import (
    ID,
    OTHER_ID,
    Clock,
    document_body,
    json_response,
    page,
    problem,
    sent_json,
    timeout_after,
)

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
    Case("invoices.create", ({"a": 1},), "POST", "/v1/invoices", body={"a": 1}),
    Case("credit_notes.create", ({"a": 1},), "POST", "/v1/credit-notes", body={"a": 1}),
    Case("debit_notes.create", ({"a": 1},), "POST", "/v1/debit-notes", body={"a": 1}),
    Case(
        "purchase_settlements.create",
        ({"a": 1},),
        "POST",
        "/v1/purchase-settlements",
        body={"a": 1},
    ),
    Case("waybills.create", ({"a": 1},), "POST", "/v1/waybills", body={"a": 1}),
    Case("withholdings.create", ({"a": 1},), "POST", "/v1/withholdings", body={"a": 1}),
    Case("documents.list", (), "GET", "/v1/documents", reply=empty_page),
    Case("documents.get", (DOCUMENT,), "GET", f"/v1/documents/{DOCUMENT}"),
    Case("documents.send_email", (DOCUMENT,), "POST", f"/v1/documents/{DOCUMENT}/email", body={}),
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


DOCUMENT_TYPES = [
    ("invoices", "/v1/invoices"),
    ("credit_notes", "/v1/credit-notes"),
    ("debit_notes", "/v1/debit-notes"),
    ("purchase_settlements", "/v1/purchase-settlements"),
    ("waybills", "/v1/waybills"),
    ("withholdings", "/v1/withholdings"),
]


def read_timeout(request: httpx.Request) -> float:
    """The per-attempt timeout the SDK gave httpx for a request."""
    return request.extensions["timeout"]["read"]


class TestIssuingDocuments:
    async def test_returns_the_document_of_a_200_and_of_a_202(self, make: MakeApi) -> None:
        api = make(
            json_response(document_body(DOCUMENT, "authorized")),
            json_response(document_body(DOCUMENT), 202),
        )
        assert (await api.op("invoices.create", {}))["status"] == "authorized"
        assert (await api.op("invoices.create", {}))["status"] == "processing"

    @pytest.mark.parametrize(("resource", "path"), DOCUMENT_TYPES)
    async def test_waits_for_the_sri_longer_than_the_client_timeout_in_sync_mode(
        self, make: MakeApi, resource: str, path: str
    ) -> None:
        api = make(json_response(document_body(DOCUMENT, "authorized")), timeout=5, max_retries=0)
        body = {"options": {"waitForAuthorization": True, "waitTimeoutSeconds": 10}}
        assert (await api.op(f"{resource}.create", body))["status"] == "authorized"
        assert api.sent[0].url.path == path
        assert read_timeout(api.sent[0]) == 25

    @pytest.mark.parametrize(
        ("options", "timeout"),
        [
            ({"waitForAuthorization": True}, 30),
            ({"waitForAuthorization": True, "waitTimeoutSeconds": 1.5}, 16.5),
            ({"waitForAuthorization": True, "waitTimeoutSeconds": None}, 30),
            ({"waitForAuthorization": True, "waitTimeoutSeconds": "20"}, 30),
            ({"waitForAuthorization": True, "waitTimeoutSeconds": True}, 30),
            ({"waitForAuthorization": False, "waitTimeoutSeconds": 30}, 5),
            ({"waitForAuthorization": "yes"}, 5),
            ({}, 5),
            (None, 5),
            ("sync", 5),
        ],
    )
    async def test_raises_the_timeout_only_for_a_sync_wait(
        self, make: MakeApi, options: object, timeout: float
    ) -> None:
        api = make(json_response(document_body(), 202), timeout=5)
        await api.op("invoices.create", {"options": options})
        assert read_timeout(api.sent[0]) == timeout

    async def test_keeps_a_longer_client_or_request_timeout(self, make: MakeApi) -> None:
        api = make(json_response({}), json_response({}), timeout=90)
        body = {"options": {"waitForAuthorization": True}}
        await api.op("invoices.create", body)
        await api.op("invoices.create", body, timeout=45)
        assert [read_timeout(request) for request in api.sent] == [90, 45]

    async def test_keeps_the_client_timeout_when_not_waiting(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(timeout_after(clock, 5), timeout=5, max_retries=0)
        with pytest.raises(APITimeoutError, match="timed out after 5 seconds"):
            await api.op("invoices.create", {"options": {"waitTimeoutSeconds": 30}})
        assert read_timeout(api.sent[0]) == 5

    async def test_sends_a_body_that_is_not_a_dict_as_it_is(self, make: MakeApi) -> None:
        api = make(json_response({}, 202))
        await api.op("invoices.create", [1, 2])
        assert sent_json(api.sent[0]) == [1, 2]

    @pytest.mark.parametrize(("resource", "path"), DOCUMENT_TYPES)
    async def test_returns_the_document_an_earlier_attempt_created(
        self, make: MakeApi, resource: str, path: str
    ) -> None:
        api = make(
            httpx.ConnectError("reset"),
            problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}),
            json_response(document_body(OTHER_ID, "authorized")),
        )
        assert (await api.op(f"{resource}.create", {}))["id"] == OTHER_ID
        assert [f"{request.method} {request.url.path}" for request in api.sent] == [
            f"POST {path}",
            f"POST {path}",
            f"GET /v1/documents/{OTHER_ID}",
        ]
        assert api.sent[0].headers["idempotency-key"] == api.sent[1].headers["idempotency-key"]

    @pytest.mark.parametrize(("resource", "path"), DOCUMENT_TYPES)
    async def test_returns_the_response_with_with_response(
        self, make: MakeApi, resource: str, path: str
    ) -> None:
        api = make(json_response(document_body(), 202, {"x-request-id": "req_issue"}))
        result = await api.op_with_response(f"{resource}.create", {})
        assert result.data["id"] == ID
        assert result.response.status_code == 202
        assert result.request_id == "req_issue"
        assert api.sent[0].url.path == path


class TestDocuments:
    async def test_returns_the_xml_and_which_stage_it_is(self, make: MakeApi) -> None:
        api = make(
            httpx.Response(
                200,
                content=b"<autorizacion/>",
                headers={"content-type": "application/xml", "flashpi-xml-kind": "authorized"},
            ),
            httpx.Response(200, content=b"<factura/>", headers={"content-type": "application/xml"}),
            httpx.Response(200, content=b"<factura/>", headers={"flashpi-xml-kind": "draft"}),
        )
        assert await api.op("documents.xml", DOCUMENT) == {
            "xml": "<autorizacion/>",
            "kind": "authorized",
        }
        assert api.sent[0].url.path == f"/v1/documents/{DOCUMENT}/xml"
        assert api.sent[0].headers["accept"] == "application/xml, application/problem+json"
        result = await api.op_with_response("documents.xml", DOCUMENT)
        assert result.data == {"xml": "<factura/>", "kind": None}
        assert result.request_id is None
        assert result.response.status_code == 200
        assert (await api.op("documents.xml", DOCUMENT))["kind"] is None

    @pytest.mark.parametrize("kind", ["authorized", "signed", "unsigned"])
    async def test_reads_every_xml_stage(self, make: MakeApi, kind: str) -> None:
        api = make(httpx.Response(200, content=b"<x/>", headers={"flashpi-xml-kind": kind}))
        assert (await api.op("documents.xml", DOCUMENT))["kind"] == kind

    async def test_returns_the_ride_as_bytes(self, make: MakeApi) -> None:
        pdf = b"%PDF\x00\xff"
        api = make(httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"}))
        assert await api.op("documents.pdf", DOCUMENT) == pdf
        assert api.sent[0].url.path == f"/v1/documents/{DOCUMENT}/pdf"
        assert api.sent[0].headers["accept"] == "application/pdf, application/problem+json"

    async def test_raises_ride_not_available_as_a_conflict_error_with_the_ride_status(
        self, make: MakeApi
    ) -> None:
        api = make(problem(409, "ride_not_available", {"rideStatus": "pending"}))
        with pytest.raises(ConflictError) as caught:
            await api.op("documents.pdf", DOCUMENT)
        assert caught.value.code == "ride_not_available"
        assert caught.value.problem is not None
        assert caught.value.problem.get("rideStatus") == "pending"
        assert len(api.sent) == 1

    async def test_lists_documents_with_their_filters(self, make: MakeApi) -> None:
        api = make(page([document_body()]))
        params = {"status": "authorized", "issueDateFrom": "2026-11-01", "limit": 50}
        first = await api.op("documents.list", params)
        assert [document["id"] for document in first.data] == [ID]
        assert dict(api.sent[0].url.params) == {
            "status": "authorized",
            "issueDateFrom": "2026-11-01",
            "limit": "50",
        }

    @pytest.mark.parametrize("name", ["list", "get", "pdf", "send_email"])
    async def test_returns_the_response_with_with_response(self, make: MakeApi, name: str) -> None:
        reply = page([]) if name == "list" else json_response({}, 202)
        api = make(reply)
        args = () if name == "list" else (DOCUMENT,)
        result = await api.op_with_response(f"documents.{name}", *args)
        assert result.request_id == "req_123"
