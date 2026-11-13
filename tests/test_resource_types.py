# pyright: reportUnnecessaryTypeIgnoreComment=error
"""What a type checker sees of the resources (Node: test/types/consumer.ts).

Pyright checks this module: `assert_type` lines must hold, and every `pyright: ignore` must hide
a real error (a misuse the types refuse). The functions are only type-checked, never run.
"""

from typing import assert_type

from flashpi import APIResponse, AsyncFlashpi, AsyncPage, AsyncPaginator, Flashpi, Page
from flashpi.types import (
    Certificate,
    CertificateUpload,
    CompletedIssuerOnboarding,
    CreateCreditNote,
    CreateInvoice,
    Document,
    DocumentXml,
    EmissionPoint,
    Event,
    Issuer,
    IssuerOnboarding,
    Status,
    WebhookDeliveryDetail,
    WebhookEndpointSecret,
)


def uses_the_sync_client(flashpi: Flashpi, invoice: CreateInvoice, note: CreateCreditNote) -> None:
    assert_type(flashpi.invoices.create(invoice), Document)
    assert_type(flashpi.credit_notes.create(note), Document)
    assert_type(flashpi.invoices.create(invoice, idempotency_key="order-1", timeout=90), Document)
    assert_type(flashpi.invoices.with_response.create(invoice), APIResponse[Document])
    assert_type(flashpi.documents.list({"status": "authorized", "limit": 50}), Page[Document])
    assert_type(flashpi.documents.xml("id"), DocumentXml)
    assert_type(flashpi.documents.pdf("id"), bytes)
    assert_type(flashpi.documents.send_email("id"), Document)
    assert_type(flashpi.issuers.get("id"), Issuer)
    assert_type(flashpi.issuers.delete("id"), None)
    assert_type(flashpi.issuers.with_response.list(), APIResponse[Page[Issuer]])
    assert_type(flashpi.issuers.establishments.emission_points.get("i", "e", "p"), EmissionPoint)
    upload: CertificateUpload = {"file": b"...", "password": "secret"}
    assert_type(flashpi.issuers.certificates.upload("id", upload), Certificate)
    assert_type(flashpi.issuer_onboardings.create(upload), IssuerOnboarding)
    assert_type(flashpi.issuer_onboardings.complete("id"), CompletedIssuerOnboarding)
    assert_type(flashpi.webhook_endpoints.get_secret("id"), WebhookEndpointSecret)
    assert_type(flashpi.webhook_endpoints.deliveries.replay("w", "d"), WebhookDeliveryDetail)
    assert_type(flashpi.events.get("id"), Event)
    assert_type(flashpi.status.get(language="es"), Status)
    for document in flashpi.documents.list():
        assert_type(document, Document)

    flashpi.invoices.create(note)  # pyright: ignore[reportArgumentType]
    flashpi.documents.list({"state": "authorized"})  # pyright: ignore[reportArgumentType]
    flashpi.documents.list({"status": "approved"})  # pyright: ignore[reportArgumentType]
    flashpi.status.get(language="fr")  # pyright: ignore[reportArgumentType]
    flashpi.status.get(retries=1)  # pyright: ignore[reportCallIssue]
    flashpi.issuers.get()  # pyright: ignore[reportCallIssue]


async def uses_the_async_client(flashpi: AsyncFlashpi, invoice: CreateInvoice) -> None:
    assert_type(await flashpi.invoices.create(invoice), Document)
    assert_type(await flashpi.invoices.with_response.create(invoice), APIResponse[Document])
    assert_type(flashpi.documents.list(), AsyncPaginator[Document])
    assert_type(await flashpi.documents.list(), AsyncPage[Document])
    assert_type(await flashpi.issuers.with_response.list(), APIResponse[AsyncPage[Issuer]])
    assert_type(await flashpi.documents.pdf("id"), bytes)
    assert_type(await flashpi.webhook_endpoints.delete("id"), None)
    async for document in flashpi.documents.list({"issuerId": "id"}):
        assert_type(document, Document)

    await flashpi.status.get(timeout="5")  # pyright: ignore[reportArgumentType]
