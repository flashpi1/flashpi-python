"""Every operation of the API's OpenAPI document maps to exactly one method of `Flashpi` and one
of `AsyncFlashpi`, which send its HTTP method, path, query parameters and body, and return its
answer with the generated type."""

import inspect
import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

import httpx
import pytest

import flashpi.types._generated as generated
from flashpi import AsyncFlashpi, AsyncPaginator, Flashpi, Page
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi.types import CertificateUpload, DocumentXml
from tests.conftest import MakeApi
from tests.support import TEST_KEY, json_response, page

pytestmark = pytest.mark.anyio

ROOT = Path(__file__).resolve().parent.parent
CONTRACT: dict[str, Any] = json.loads((ROOT / "openapi" / "openapi.json").read_text("utf-8"))

OPERATIONS: dict[str, str] = {
    "statusGet": "status.get",
    "issuersCreate": "issuers.create",
    "issuersList": "issuers.list",
    "issuersGet": "issuers.get",
    "issuersUpdate": "issuers.update",
    "issuersDelete": "issuers.delete",
    "establishmentsCreate": "issuers.establishments.create",
    "establishmentsList": "issuers.establishments.list",
    "establishmentsGet": "issuers.establishments.get",
    "establishmentsUpdate": "issuers.establishments.update",
    "establishmentsDelete": "issuers.establishments.delete",
    "emissionPointsCreate": "issuers.establishments.emission_points.create",
    "emissionPointsList": "issuers.establishments.emission_points.list",
    "emissionPointsGet": "issuers.establishments.emission_points.get",
    "emissionPointsDelete": "issuers.establishments.emission_points.delete",
    "certificatesUpload": "issuers.certificates.upload",
    "certificatesList": "issuers.certificates.list",
    "certificatesGet": "issuers.certificates.get",
    "issuerOnboardingsCreate": "issuer_onboardings.create",
    "issuerOnboardingsGet": "issuer_onboardings.get",
    "issuerOnboardingsComplete": "issuer_onboardings.complete",
    "invoicesCreate": "invoices.create",
    "creditNotesCreate": "credit_notes.create",
    "debitNotesCreate": "debit_notes.create",
    "purchaseSettlementsCreate": "purchase_settlements.create",
    "waybillsCreate": "waybills.create",
    "withholdingsCreate": "withholdings.create",
    "documentsList": "documents.list",
    "documentsGet": "documents.get",
    "documentsGetXml": "documents.xml",
    "documentsGetPdf": "documents.pdf",
    "documentsSendEmail": "documents.send_email",
    "webhookEndpointsCreate": "webhook_endpoints.create",
    "webhookEndpointsList": "webhook_endpoints.list",
    "webhookEndpointsGet": "webhook_endpoints.get",
    "webhookEndpointsUpdate": "webhook_endpoints.update",
    "webhookEndpointsDelete": "webhook_endpoints.delete",
    "webhookEndpointsSecret": "webhook_endpoints.get_secret",
    "webhookEndpointsRotateSecret": "webhook_endpoints.rotate_secret",
    "webhookEndpointsVerify": "webhook_endpoints.verify",
    "webhookEndpointsDeliveriesList": "webhook_endpoints.deliveries.list",
    "webhookEndpointsDeliveriesGet": "webhook_endpoints.deliveries.get",
    "webhookEndpointsDeliveriesReplay": "webhook_endpoints.deliveries.replay",
    "eventsList": "events.list",
    "eventsGet": "events.get",
}
"""Each operationId of the contract and the resource method that sends it."""

EMPTY_BODY_ALLOWED = {"issuerOnboardingsComplete"}
"""Operations whose body the contract requires but whose method may leave out: `{}` is a valid
body (completing the renewal of an existing issuer), as in the Node SDK."""

P12 = bytes([0x30, 0x82, 0x01, 0x02])


@dataclass(frozen=True)
class Operation:
    """An operation as the contract describes it."""

    id: str
    method: str
    path: str
    query: dict[str, dict[str, Any]]
    """Query parameters: name to schema."""
    body_type: str | None
    """Content type of the request body, if any."""
    body_required: bool
    body_schema: str | None
    """The component schema of a JSON body."""
    status: int
    """The first success status."""
    answer_type: str | None
    """Content type of the success answer (None for 204)."""
    answer_schema: str | None
    """The component schema of a JSON answer."""
    idempotent_post: bool
    """Whether the operation takes an Idempotency-Key header."""


def schema_name(schema: dict[str, Any] | None) -> str | None:
    reference = (schema or {}).get("$ref")
    return reference.rsplit("/", 1)[-1] if isinstance(reference, str) else None


def contract_operations() -> dict[str, Operation]:
    operations: dict[str, Operation] = {}
    for path, item in CONTRACT["paths"].items():
        for method, spec in item.items():
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            parameters = [*item.get("parameters", []), *spec.get("parameters", [])]
            content = spec.get("requestBody", {}).get("content", {})
            body_type = next(iter(content), None)
            status, answer = min(
                (int(code), answer)
                for code, answer in spec["responses"].items()
                if code.startswith("2")
            )
            answer_content = answer.get("content", {})
            answer_type = next(iter(answer_content), None)
            operations[spec["operationId"]] = Operation(
                id=spec["operationId"],
                method=method.upper(),
                path=path,
                query={p["name"]: p["schema"] for p in parameters if p.get("in") == "query"},
                body_type=body_type,
                body_required=spec.get("requestBody", {}).get("required") is True,
                body_schema=schema_name(content.get(body_type, {}).get("schema")),
                status=status,
                answer_type=answer_type,
                answer_schema=schema_name(answer_content.get(answer_type, {}).get("schema")),
                idempotent_post=any(p.get("name") == "Idempotency-Key" for p in parameters),
            )
    return operations


CONTRACT_OPERATIONS = contract_operations()


def resources(client: object, prefix: str = "") -> Iterator[tuple[str, Any]]:
    """Every resource of a client (or of a resource), by dotted name."""
    for name, value in vars(client).items():
        if isinstance(value, SyncAPIResource | AsyncAPIResource):
            yield f"{prefix}{name}", value
            yield from resources(value, f"{prefix}{name}.")


def public_methods(resource: object) -> list[str]:
    return [
        name
        for name, _ in inspect.getmembers(type(resource), inspect.isfunction)
        if not name.startswith("_")
    ]


def operation_methods(client: object) -> list[str]:
    """Every public method of every resource of a client, by dotted name."""
    return [
        f"{name}.{method}"
        for name, resource in resources(client)
        for method in public_methods(resource)
    ]


def resolve(client: object, dotted: str) -> Any:
    target: Any = client
    for attribute in dotted.split("."):
        target = getattr(target, attribute)
    return target


def snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


@pytest.fixture(scope="module")
def clients() -> Iterator[tuple[Flashpi, AsyncFlashpi]]:
    sync = Flashpi(TEST_KEY)
    yield sync, AsyncFlashpi(TEST_KEY)
    sync.close()


def test_maps_every_operation_of_the_contract_to_its_own_method() -> None:
    assert sorted(OPERATIONS) == sorted(CONTRACT_OPERATIONS)
    assert len(CONTRACT_OPERATIONS) == 45
    assert len(set(OPERATIONS.values())) == len(OPERATIONS)


@pytest.mark.parametrize("index", [0, 1], ids=["Flashpi", "AsyncFlashpi"])
def test_every_method_of_the_resources_is_one_operation(
    clients: tuple[Flashpi, AsyncFlashpi], index: int
) -> None:
    methods = operation_methods(clients[index])
    assert len(methods) == len(set(methods))
    assert sorted(methods) == sorted(OPERATIONS.values())


@pytest.mark.parametrize("index", [0, 1], ids=["Flashpi", "AsyncFlashpi"])
def test_every_resource_has_a_with_response_view_of_its_methods(
    clients: tuple[Flashpi, AsyncFlashpi], index: int
) -> None:
    for name, resource in resources(clients[index]):
        view: object = resource.with_response
        assert sorted(vars(view)) == sorted(public_methods(resource)), name
        assert resource.with_response is view


def resolved_hints(method: Any) -> dict[str, Any]:
    """The annotations of a method, with the document type of a DocumentIssuer filled in."""
    hints: dict[str, Any] = get_type_hints(method)
    instance: object = method.__self__
    owner = type(instance)
    bases: tuple[Any, ...] = getattr(owner, "__orig_bases__", ())
    for base in bases:
        arguments = get_args(base)
        if arguments:
            hints = {
                name: arguments[0] if isinstance(hint, TypeVar) else hint
                for name, hint in hints.items()
            }
    return hints


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_the_signatures_follow_the_contract(
    clients: tuple[Flashpi, AsyncFlashpi], operation_id: str
) -> None:
    operation = CONTRACT_OPERATIONS[operation_id]
    sync = resolve(clients[0], OPERATIONS[operation_id])
    async_ = resolve(clients[1], OPERATIONS[operation_id])
    sync_signature = inspect.signature(sync)
    async_signature = inspect.signature(async_)
    hints = resolved_hints(sync)

    # The same parameters on both clients: the path ids in order, then the body or filters.
    assert list(sync_signature.parameters.values()) == list(async_signature.parameters.values())
    parameters = list(sync_signature.parameters.values())
    assert parameters[-1].kind is inspect.Parameter.VAR_KEYWORD
    ids = [parameter.name for parameter in parameters if parameter.name.endswith("_id")]
    placeholders = re.findall(r"\{(\w+)\}", operation.path)
    assert ids == [snake_case(name) for name in placeholders]
    others = [p for p in parameters[:-1] if p.name not in ids]
    assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in parameters[:-1])

    if operation.query:
        assert [p.name for p in others] == ["params"]
        assert others[0].default is None
        query_type = next(arg for arg in get_args(hints["params"]) if arg is not type(None))
        assert sorted(get_type_hints(query_type)) == sorted(operation.query)
    elif operation.body_type == "multipart/form-data":
        assert [p.name for p in others] == ["upload"]
        assert hints["upload"] is CertificateUpload
    elif operation.body_type is not None and others:
        assert [p.name for p in others] == ["body"]
        expected = getattr(generated, str(operation.body_schema))
        optional = not operation.body_required or operation_id in EMPTY_BODY_ALLOWED
        assert hints["body"] == (expected | None if optional else expected)
        assert (others[0].default is None) == optional
    else:
        # documents.send_email: its body has no members yet, so the method always sends {}.
        assert others == []
        assert operation.body_type is None or not operation.body_required

    # The answer, as its generated type.
    if operation.answer_type is None:
        answer: Any = type(None)
    elif operation.answer_type == "application/xml":
        answer = DocumentXml
    elif operation.answer_type == "application/pdf":
        answer = bytes
    else:
        answer = getattr(generated, str(operation.answer_schema))
    returned = hints["return"]
    if get_origin(returned) is Page:
        item = get_type_hints(answer)["data"]
        assert returned == Page[get_args(item)[0]]
        assert get_type_hints(async_)["return"] == AsyncPaginator[get_args(item)[0]]
        assert not inspect.iscoroutinefunction(async_)
    else:
        assert returned == answer
        assert inspect.iscoroutinefunction(async_)
        assert not inspect.iscoroutinefunction(sync)


def sample(schema: dict[str, Any]) -> Any:
    """A valid query value for a schema."""
    if "enum" in schema:
        return schema["enum"][0]
    return 7 if schema.get("type") == "integer" else "v"


def answer_of(operation: Operation) -> Callable[[], httpx.Response]:
    if operation.answer_type is None:
        return lambda: httpx.Response(operation.status)
    if operation.answer_type in ("application/xml", "application/pdf"):
        return lambda: httpx.Response(
            operation.status,
            content=b"<x/>" if operation.answer_type == "application/xml" else b"%PDF-",
            headers={"content-type": str(operation.answer_type)},
        )
    if operation.query:
        return lambda: page([])
    return lambda: json_response({}, operation.status)


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
async def test_sends_the_operation_of_the_contract(make: MakeApi, operation_id: str) -> None:
    operation = CONTRACT_OPERATIONS[operation_id]
    api = make(answer_of(operation)())
    method = api.method(OPERATIONS[operation_id])
    arguments: list[Any] = []
    path = operation.path
    query: dict[str, Any] = {}
    for parameter in list(inspect.signature(method).parameters.values())[:-1]:
        if parameter.name.endswith("_id"):
            value = f"id{len(arguments) + 1}"
            path = re.sub(r"\{\w+\}", value, path, count=1)
            arguments.append(value)
        elif parameter.name == "params":
            query = {name: sample(schema) for name, schema in operation.query.items()}
            arguments.append(query)
        elif parameter.name == "upload":
            arguments.append({"file": P12, "password": "x"})
        else:
            assert parameter.name == "body"
            arguments.append({})
    result = await api.op(OPERATIONS[operation_id], *arguments)

    assert len(api.sent) == 1
    request = api.sent[0]
    assert request.method == operation.method
    assert request.url.path == path
    assert dict(request.url.params) == {name: str(value) for name, value in query.items()}
    content_type = request.headers.get("content-type", "")
    if operation.body_type is None:
        assert (request.content, content_type) == (b"", "")
    elif operation.body_type == "multipart/form-data":
        assert content_type.startswith("multipart/form-data; boundary=")
    else:
        assert content_type == operation.body_type
        assert json.loads(request.content) == {}
    accept = request.headers["accept"].split(",")[0]
    assert accept == (operation.answer_type or "application/json")
    assert ("idempotency-key" in request.headers) == operation.idempotent_post
    assert operation.idempotent_post == (operation.method == "POST")
    if operation.answer_type is None:
        assert result is None
