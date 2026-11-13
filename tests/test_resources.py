"""Every resource method sends its operation (Node: test/resources.test.ts)."""

import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import HTTP
from pathlib import Path
from typing import Any

import httpx
import pytest

from flashpi import APIResponse, APITimeoutError, ConflictError, FlashpiError
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
    Case("issuers.create", ({"ruc": "1"},), "POST", "/v1/issuers", body={"ruc": "1"}),
    Case("issuers.list", (), "GET", "/v1/issuers", reply=empty_page),
    Case("issuers.get", (ISSUER,), "GET", f"/v1/issuers/{ISSUER}"),
    Case(
        "issuers.update",
        (ISSUER, {"tradeName": "X"}),
        "PATCH",
        f"/v1/issuers/{ISSUER}",
        body={"tradeName": "X"},
    ),
    Case("issuers.delete", (ISSUER,), "DELETE", f"/v1/issuers/{ISSUER}", reply=no_content),
    Case(
        "issuers.establishments.create",
        (ISSUER, {"code": "002"}),
        "POST",
        f"/v1/issuers/{ISSUER}/establishments",
        body={"code": "002"},
    ),
    Case(
        "issuers.establishments.list",
        (ISSUER,),
        "GET",
        f"/v1/issuers/{ISSUER}/establishments",
        reply=empty_page,
    ),
    Case(
        "issuers.establishments.get",
        (ISSUER, ESTABLISHMENT),
        "GET",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}",
    ),
    Case(
        "issuers.establishments.update",
        (ISSUER, ESTABLISHMENT, {"address": "Quito"}),
        "PATCH",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}",
        body={"address": "Quito"},
    ),
    Case(
        "issuers.establishments.delete",
        (ISSUER, ESTABLISHMENT),
        "DELETE",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}",
        reply=no_content,
    ),
    Case(
        "issuers.establishments.emission_points.create",
        (ISSUER, ESTABLISHMENT, {"code": "002"}),
        "POST",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}/emission-points",
        body={"code": "002"},
    ),
    Case(
        "issuers.establishments.emission_points.list",
        (ISSUER, ESTABLISHMENT),
        "GET",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}/emission-points",
        reply=empty_page,
    ),
    Case(
        "issuers.establishments.emission_points.get",
        (ISSUER, ESTABLISHMENT, POINT),
        "GET",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}/emission-points/{POINT}",
    ),
    Case(
        "issuers.establishments.emission_points.delete",
        (ISSUER, ESTABLISHMENT, POINT),
        "DELETE",
        f"/v1/issuers/{ISSUER}/establishments/{ESTABLISHMENT}/emission-points/{POINT}",
        reply=no_content,
    ),
    Case(
        "issuers.certificates.list",
        (ISSUER,),
        "GET",
        f"/v1/issuers/{ISSUER}/certificates",
        reply=empty_page,
    ),
    Case(
        "issuers.certificates.get",
        (ISSUER, CERTIFICATE),
        "GET",
        f"/v1/issuers/{ISSUER}/certificates/{CERTIFICATE}",
    ),
    Case("issuer_onboardings.get", (ONBOARDING,), "GET", f"/v1/issuer-onboardings/{ONBOARDING}"),
    Case(
        "issuer_onboardings.complete",
        (ONBOARDING,),
        "POST",
        f"/v1/issuer-onboardings/{ONBOARDING}/complete",
        body={},
        label="issuer_onboardings.complete (empty body by default)",
    ),
    Case(
        "issuer_onboardings.complete",
        (ONBOARDING, {"ruc": "1790012345001"}),
        "POST",
        f"/v1/issuer-onboardings/{ONBOARDING}/complete",
        body={"ruc": "1790012345001"},
    ),
    Case(
        "webhook_endpoints.create",
        ({"url": "https://x"},),
        "POST",
        "/v1/webhook-endpoints",
        body={"url": "https://x"},
    ),
    Case("webhook_endpoints.list", (), "GET", "/v1/webhook-endpoints", reply=empty_page),
    Case("webhook_endpoints.get", (ENDPOINT,), "GET", f"/v1/webhook-endpoints/{ENDPOINT}"),
    Case(
        "webhook_endpoints.update",
        (ENDPOINT, {"disabled": True}),
        "PATCH",
        f"/v1/webhook-endpoints/{ENDPOINT}",
        body={"disabled": True},
    ),
    Case(
        "webhook_endpoints.delete",
        (ENDPOINT,),
        "DELETE",
        f"/v1/webhook-endpoints/{ENDPOINT}",
        reply=no_content,
    ),
    Case(
        "webhook_endpoints.get_secret",
        (ENDPOINT,),
        "GET",
        f"/v1/webhook-endpoints/{ENDPOINT}/secret",
    ),
    Case(
        "webhook_endpoints.rotate_secret",
        (ENDPOINT, {"previousSecretExpiresInHours": 0}),
        "POST",
        f"/v1/webhook-endpoints/{ENDPOINT}/rotate-secret",
        body={"previousSecretExpiresInHours": 0},
    ),
    Case(
        "webhook_endpoints.rotate_secret",
        (ENDPOINT,),
        "POST",
        f"/v1/webhook-endpoints/{ENDPOINT}/rotate-secret",
        label="webhook_endpoints.rotate_secret (no body)",
    ),
    Case(
        "webhook_endpoints.verify",
        (ENDPOINT,),
        "POST",
        f"/v1/webhook-endpoints/{ENDPOINT}/verify",
    ),
    Case(
        "webhook_endpoints.deliveries.list",
        (ENDPOINT, {"status": "failed"}),
        "GET",
        f"/v1/webhook-endpoints/{ENDPOINT}/deliveries",
        query={"status": "failed"},
        reply=empty_page,
    ),
    Case(
        "webhook_endpoints.deliveries.get",
        (ENDPOINT, DELIVERY),
        "GET",
        f"/v1/webhook-endpoints/{ENDPOINT}/deliveries/{DELIVERY}",
    ),
    Case(
        "webhook_endpoints.deliveries.replay",
        (ENDPOINT, DELIVERY),
        "POST",
        f"/v1/webhook-endpoints/{ENDPOINT}/deliveries/{DELIVERY}/replay",
    ),
]


def test_covers_the_45_operations_of_the_api() -> None:
    # issuers.certificates.upload, issuer_onboardings.create, documents.xml and documents.pdf
    # have their own tests below; test_operations.py checks every one against the contract.
    operations = {(case.method, case.path) for case in CASES}
    assert len(operations) + 4 == 45


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


P12 = bytes([0x30, 0x82, 0x01, 0x02])
"""The start of a .p12 (a DER sequence): enough for the SDK, which never parses it."""

Part = tuple[str | None, str | None, str | None, bytes]


def sent_form(request: httpx.Request) -> list[Part]:
    """The parts of a multipart request: (name, file name, content type, content)."""
    content_type = request.headers["content-type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    head = f"Content-Type: {content_type}\r\n\r\n".encode()
    message = BytesParser(policy=HTTP).parsebytes(head + request.content)
    parts: list[Part] = []
    for part in message.iter_parts():
        payload = part.get_payload(decode=True)
        assert isinstance(payload, bytes)
        name = part.get_param("name", header="content-disposition")
        parts.append(
            (
                name if isinstance(name, str) else None,
                part.get_filename(),
                part["content-type"],
                payload,
            )
        )
    return parts


class TestCertificateUploads:
    async def test_uploads_a_certificate_as_multipart_with_the_file_and_the_password(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({"id": CERTIFICATE, "status": "processing"}, 202))
        certificate = await api.op(
            "issuers.certificates.upload", ISSUER, {"file": P12, "password": "secret ñ"}
        )
        assert certificate["id"] == CERTIFICATE
        request = api.sent[0]
        assert request.method == "POST"
        assert request.url.path == f"/v1/issuers/{ISSUER}/certificates"
        assert "idempotency-key" in request.headers
        assert sent_form(request) == [
            ("password", None, None, "secret ñ".encode()),
            ("file", "certificate.p12", "application/x-pkcs12", P12),
        ]

    @pytest.mark.parametrize(
        "file",
        [bytearray(P12), memoryview(P12), io.BytesIO(P12)],
        ids=["bytearray", "memoryview", "binary file"],
    )
    async def test_takes_bytes_like_values_and_binary_files(
        self, make: MakeApi, file: object
    ) -> None:
        if isinstance(file, io.BytesIO):
            file.seek(0)
        api = make(json_response({"id": CERTIFICATE}, 202))
        upload = {"file": file, "password": "x", "filename": "firma.p12"}
        await api.op("issuers.certificates.upload", ISSUER, upload)
        assert sent_form(api.sent[0])[1] == ("file", "firma.p12", "application/x-pkcs12", P12)

    async def test_reads_a_file_opened_from_disk(self, make: MakeApi, tmp_path: Path) -> None:
        path = tmp_path / "firma.p12"
        path.write_bytes(P12)
        api = make(json_response({"id": CERTIFICATE}, 202))
        with path.open("rb") as file:
            await api.op("issuers.certificates.upload", ISSUER, {"file": file, "password": "x"})
        assert sent_form(api.sent[0])[1][3] == P12

    async def test_sends_the_same_file_again_on_a_retry(self, make: MakeApi) -> None:
        api = make(problem(500, "internal_error"), json_response({"id": CERTIFICATE}, 202))
        upload = {"file": io.BytesIO(P12), "password": "x"}
        await api.op("issuers.certificates.upload", ISSUER, upload)
        assert len(api.sent) == 2
        assert api.sent[0].headers["idempotency-key"] == api.sent[1].headers["idempotency-key"]
        assert [sent_form(request)[1][3] for request in api.sent] == [P12, P12]

    async def test_accepts_a_file_of_exactly_1_mib(self, make: MakeApi) -> None:
        api = make(json_response({"id": CERTIFICATE}, 202))
        upload = {"file": bytes(1_048_576), "password": "x"}
        await api.op("issuers.certificates.upload", ISSUER, upload)
        assert len(sent_form(api.sent[0])[1][3]) == 1_048_576

    @pytest.mark.parametrize(
        ("upload", "error", "message"),
        [
            ({"file": b"", "password": "x"}, FlashpiError, "empty"),
            ({"file": io.BytesIO(), "password": "x"}, FlashpiError, "empty"),
            ({"file": bytes(1_048_577), "password": "x"}, FlashpiError, "1048577 bytes.*1048576"),
            ({"file": P12}, FlashpiError, "password must be a string"),
            ({"file": P12, "password": None}, FlashpiError, "password must be a string"),
            ({"file": P12, "password": b"x"}, FlashpiError, "password must be a string"),
            ({"password": "x"}, TypeError, "got NoneType"),
            ({"file": "firma.p12", "password": "x"}, TypeError, "binary mode"),
            ({"file": io.StringIO("x"), "password": "x"}, TypeError, "got StringIO"),
            ({"file": P12, "password": "x", "filename": 1}, TypeError, "filename"),
            (P12, TypeError, "must be a dict"),
        ],
    )
    async def test_refuses_a_bad_upload_before_sending(
        self, make: MakeApi, upload: object, error: type[Exception], message: str
    ) -> None:
        api = make()
        with pytest.raises(error, match=message):
            await api.op("issuers.certificates.upload", ISSUER, upload)
        assert api.sent == []


EMPTY: dict[str, Any] = {}

ISSUER_CALLS: list[tuple[str, tuple[Any, ...], Callable[[], httpx.Response]]] = [
    ("issuers.create", (EMPTY,), empty_object),
    ("issuers.list", (), empty_page),
    ("issuers.get", (ISSUER,), empty_object),
    ("issuers.update", (ISSUER, EMPTY), empty_object),
    ("issuers.delete", (ISSUER,), no_content),
    ("issuers.establishments.create", (ISSUER, EMPTY), empty_object),
    ("issuers.establishments.list", (ISSUER,), empty_page),
    ("issuers.establishments.get", (ISSUER, ESTABLISHMENT), empty_object),
    ("issuers.establishments.update", (ISSUER, ESTABLISHMENT, EMPTY), empty_object),
    ("issuers.establishments.delete", (ISSUER, ESTABLISHMENT), no_content),
    (
        "issuers.establishments.emission_points.create",
        (ISSUER, ESTABLISHMENT, EMPTY),
        empty_object,
    ),
    ("issuers.establishments.emission_points.list", (ISSUER, ESTABLISHMENT), empty_page),
    (
        "issuers.establishments.emission_points.get",
        (ISSUER, ESTABLISHMENT, POINT),
        empty_object,
    ),
    (
        "issuers.establishments.emission_points.delete",
        (ISSUER, ESTABLISHMENT, POINT),
        no_content,
    ),
    ("issuers.certificates.upload", (ISSUER, {"file": P12, "password": "x"}), empty_object),
    ("issuers.certificates.list", (ISSUER,), empty_page),
    ("issuers.certificates.get", (ISSUER, CERTIFICATE), empty_object),
]


class TestIssuers:
    @pytest.mark.parametrize(
        ("name", "args"),
        [
            ("issuers.list", ()),
            ("issuers.establishments.list", (ISSUER,)),
            ("issuers.establishments.emission_points.list", (ISSUER, ESTABLISHMENT)),
            ("issuers.certificates.list", (ISSUER,)),
        ],
    )
    async def test_lists_with_paging(self, make: MakeApi, name: str, args: tuple[str, ...]) -> None:
        api = make(page([{"id": "a"}], "next"), page([{"id": "b"}]))
        first = await api.op(name, *args, {"limit": 1})
        assert [item["id"] for item in await api.iterate(first)] == ["a", "b"]
        assert [dict(request.url.params) for request in api.sent] == [
            {"limit": "1"},
            {"limit": "1", "cursor": "next"},
        ]

    @pytest.mark.parametrize(("name", "args", "reply"), ISSUER_CALLS)
    async def test_returns_the_response_with_with_response(
        self, make: MakeApi, name: str, args: tuple[Any, ...], reply: Callable[[], httpx.Response]
    ) -> None:
        api = make(reply())
        result = await api.op_with_response(name, *args)
        assert isinstance(result, APIResponse)
        assert result.response.request.url.path == api.sent[0].url.path


class TestIssuerOnboardings:
    async def test_starts_an_onboarding_with_a_binary_file_and_a_file_name(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({"id": ONBOARDING}, 202), json_response({"id": ONBOARDING}, 202))
        upload = {"file": io.BytesIO(P12), "password": "x", "filename": "firma.p12"}
        assert (await api.op("issuer_onboardings.create", upload))["id"] == ONBOARDING
        await api.op("issuer_onboardings.create", {"file": P12, "password": "x"})
        assert [request.url.path for request in api.sent] == ["/v1/issuer-onboardings"] * 2
        assert all("idempotency-key" in request.headers for request in api.sent)
        assert sent_form(api.sent[0]) == [
            ("password", None, None, b"x"),
            ("file", "firma.p12", "application/x-pkcs12", P12),
        ]
        assert sent_form(api.sent[1])[1][1:] == ("certificate.p12", "application/x-pkcs12", P12)

    async def test_refuses_a_missing_password_before_sending(self, make: MakeApi) -> None:
        api = make()
        with pytest.raises(FlashpiError, match="password"):
            await api.op("issuer_onboardings.create", {"file": P12})
        assert api.sent == []

    @pytest.mark.parametrize(
        ("name", "args"),
        [
            ("create", ({"file": P12, "password": "x"},)),
            ("get", (ONBOARDING,)),
            ("complete", (ONBOARDING,)),
        ],
    )
    async def test_returns_the_response_with_with_response(
        self, make: MakeApi, name: str, args: tuple[Any, ...]
    ) -> None:
        api = make(json_response({"id": ONBOARDING}, 201))
        result = await api.op_with_response(f"issuer_onboardings.{name}", *args)
        assert (result.data, result.response.status_code) == ({"id": ONBOARDING}, 201)


WEBHOOK_CALLS: list[tuple[str, tuple[Any, ...], Callable[[], httpx.Response]]] = [
    ("webhook_endpoints.create", (EMPTY,), empty_object),
    ("webhook_endpoints.list", (), empty_page),
    ("webhook_endpoints.get", (ENDPOINT,), empty_object),
    ("webhook_endpoints.update", (ENDPOINT, EMPTY), empty_object),
    ("webhook_endpoints.delete", (ENDPOINT,), no_content),
    ("webhook_endpoints.get_secret", (ENDPOINT,), empty_object),
    ("webhook_endpoints.rotate_secret", (ENDPOINT,), empty_object),
    ("webhook_endpoints.verify", (ENDPOINT,), empty_object),
    ("webhook_endpoints.deliveries.list", (ENDPOINT,), empty_page),
    ("webhook_endpoints.deliveries.get", (ENDPOINT, DELIVERY), empty_object),
    ("webhook_endpoints.deliveries.replay", (ENDPOINT, DELIVERY), empty_object),
]


class TestWebhookEndpoints:
    async def test_reads_the_signing_secret(self, make: MakeApi) -> None:
        secret = {"secret": "whsec_abc", "previousSecretExpiresAt": None}
        api = make(json_response(secret))
        assert await api.op("webhook_endpoints.get_secret", ENDPOINT) == secret

    async def test_walks_the_deliveries_of_an_endpoint(self, make: MakeApi) -> None:
        api = make(page([{"id": "del_1"}], "c1"), page([{"id": "del_2"}]))
        params = {"status": "failed", "eventType": "invoice.authorized", "eventId": EVENT}
        first = await api.op("webhook_endpoints.deliveries.list", ENDPOINT, params)
        assert [delivery["id"] for delivery in await api.iterate(first)] == ["del_1", "del_2"]
        assert dict(api.sent[1].url.params) == {**params, "cursor": "c1"}
        assert api.sent[1].url.path == f"/v1/webhook-endpoints/{ENDPOINT}/deliveries"

    @pytest.mark.parametrize(("name", "args", "reply"), WEBHOOK_CALLS)
    async def test_returns_the_response_with_with_response(
        self, make: MakeApi, name: str, args: tuple[Any, ...], reply: Callable[[], httpx.Response]
    ) -> None:
        api = make(reply())
        result = await api.op_with_response(name, *args)
        assert isinstance(result, APIResponse)
        assert result.response.request.url.path == api.sent[0].url.path
