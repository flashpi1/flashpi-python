"""The public types. Pyright checks the static parts (`assert_type`, narrowing) of this file."""

import json
from pathlib import Path
from typing import Any, assert_type, get_args

import flashpi.types
from flashpi.types import (
    AccountEmailSending,
    AccountEventType,
    ApiFieldErrorCode,
    Certificate,
    CertificateEventType,
    Document,
    DocumentEventType,
    DocumentListParams,
    DocumentXml,
    Environment,
    Event,
    EventType,
    FieldError,
    Problem,
    ThinWebhookEvent,
    WebhookEndpointVerificationEventData,
    WebhookEvent,
)
from flashpi.types._generated import EventThinType

ROOT = Path(__file__).resolve().parent.parent
CONTRACT: dict[str, Any] = json.loads((ROOT / "openapi" / "openapi.json").read_text("utf-8"))


def literals(annotation: object) -> list[str]:
    """The values of a Literal, or of a union of Literals."""
    arguments = get_args(annotation)
    if all(isinstance(argument, str) for argument in arguments):
        return [str(argument) for argument in arguments]
    return [value for argument in arguments for value in literals(argument)]


def test_event_types_cover_every_webhook_the_api_documents() -> None:
    webhooks = set(CONTRACT["webhooks"]) - {"webhook_endpoint.verification"}
    event_types = literals(EventType)
    assert set(event_types) == webhooks
    assert len(event_types) == len(webhooks)
    assert set(literals(EventThinType)) == webhooks
    by_group = literals(DocumentEventType) + literals(CertificateEventType)
    assert sorted(by_group + literals(AccountEventType)) == sorted(webhooks)


def test_environments_and_list_params() -> None:
    assert get_args(Environment) == ("test", "live")
    params: DocumentListParams = {"status": "authorized", "issueDateFrom": "2026-11-01"}
    assert params["status"] == "authorized"


def test_every_public_name_is_exported() -> None:
    for name in flashpi.types.__all__:
        assert getattr(flashpi.types, name) is not None


# Static checks: narrowing on "type" gives the matching "data".


def narrows_an_event(event: Event) -> None:
    if event["type"] == "withholding.rejected":
        assert_type(event["data"], Document)
    if event["type"] == "certificate.pending":
        assert_type(event["data"], Certificate)
    if event["type"] == "account.email_resumed":
        assert_type(event["data"], AccountEmailSending)


def narrows_a_webhook(event: WebhookEvent) -> str | None:
    if event["type"] == "webhook_endpoint.verification":
        assert_type(event["data"], WebhookEndpointVerificationEventData)
        return event["data"]["challenge"]
    if event["type"] == "invoice.authorized" or event["type"] == "document.email.bounced":
        assert_type(event["data"], Document)
        return event["data"]["accessKey"]
    return None


def reads_a_thin_webhook(event: ThinWebhookEvent) -> str:
    if event["type"] == "webhook_endpoint.verification":
        return event["data"]["challenge"]
    return event["id"]


def keeps_field_error_codes_open(error: FieldError, problem: Problem) -> None:
    assert_type(error["code"], ApiFieldErrorCode)
    code: ApiFieldErrorCode = "a_code_added_later"
    assert code
    assert_type(problem.get("documentId"), str | None)
    assert_type(problem.get("limit"), int | None)


def test_the_static_checks_run() -> None:
    document: Document = json.loads('{"accessKey": "1"}')
    xml: DocumentXml = {"xml": "<factura/>", "kind": None}
    challenge: WebhookEvent = {
        "id": "1",
        "type": "webhook_endpoint.verification",
        "environment": "test",
        "createdAt": "2026-10-16T17:20:00.000Z",
        "data": {"webhookEndpointId": "2", "challenge": "c"},
    }
    assert narrows_a_webhook(challenge) == "c"
    assert reads_a_thin_webhook(challenge) == "c"
    narrows_an_event(
        {
            "id": "1",
            "type": "invoice.authorized",
            "environment": "test",
            "createdAt": "2026-10-16T17:20:00.000Z",
            "data": document,
        }
    )
    keeps_field_error_codes_open(
        {"field": "items[0]", "code": "required", "message": "Required"},
        json.loads('{"code": "not_found"}'),
    )
    assert xml["kind"] is None
