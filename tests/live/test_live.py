"""The SDK against the real Flashpi API in test mode (SRI pruebas), port of the Node SDK's
test/live/live.test.ts:

    uv run pytest -m live --no-cov

Needs FLASHPI_TEST_API_KEY (an fp_test_ key with read_write access) and FLASHPI_DEMO_ISSUER_ID
(the demo issuer's id, on the console's Overview); FLASHPI_BASE_URL may point to another API.
Without them every test is skipped, and the normal run (`-m "not live"`) leaves them out. It
issues ONE real test invoice on the shared demo issuer, which counts toward its daily quota of
50, so CI only runs it while a release is being prepared. It never accepts an fp_live_ key.

The tests run in order and share the invoice.
"""

import asyncio
import os
import re
import time
import uuid
from collections.abc import Iterator, Mapping

import pytest

from flashpi import AsyncFlashpi, ConflictError, Flashpi, NotFoundError, UnprocessableEntityError
from flashpi.types import CreateInvoice, Document

API_KEY = os.environ.get("FLASHPI_TEST_API_KEY", "")
ISSUER_ID = os.environ.get("FLASHPI_DEMO_ISSUER_ID", "")
BASE_URL = os.environ.get("FLASHPI_BASE_URL") or None

IDEMPOTENCY_KEY = f"sdk-live-python-{int(time.time()):x}-{uuid.uuid4()}"
POLLS = 24
"""Checks of a slow SRI step, 5 seconds apart: up to 2 minutes."""

pytestmark = [
    pytest.mark.live,
    pytest.mark.anyio,
    pytest.mark.skipif(
        not (API_KEY and ISSUER_ID), reason="needs FLASHPI_TEST_API_KEY and FLASHPI_DEMO_ISSUER_ID"
    ),
]

issued: list[Document] = []
"""The invoice the suite issues, once it is authorized."""


def sample_invoice() -> CreateInvoice:
    """The same test invoice as the docs' quickstart: USD 1.00 + 15 % VAT to the SRI's test
    RUC."""
    return {
        "issuerId": ISSUER_ID,
        "establishment": "001",
        "emissionPoint": "001",
        "customer": {
            "idType": "ruc",
            "id": "1760013210001",
            "name": "PRUEBAS SERVICIO DE RENTAS INTERNAS",
            "address": "AMAZONAS AVENUE AND VILLALENGUA, QUITO",
        },
        "items": [
            {
                "code": "SDK-LIVE-001",
                "description": "flashpi (Python) live test",
                "quantity": "1",
                "unitPrice": "1.00",
                "taxes": [{"type": "vat", "rate": "15"}],
            }
        ],
        "payments": [{"method": "cash", "amount": "1.15"}],
        "options": {"waitForAuthorization": True, "waitTimeoutSeconds": 30, "sendEmail": False},
    }


def checked_key() -> str:
    if not API_KEY.startswith("fp_test_"):
        raise RuntimeError(
            "FLASHPI_TEST_API_KEY must be an fp_test_ key: this suite never runs live"
        )
    return API_KEY


@pytest.fixture(scope="module")
def flashpi() -> Iterator[Flashpi]:
    with Flashpi(checked_key(), base_url=BASE_URL) as client:
        yield client


@pytest.fixture
def invoice() -> Document:
    if not issued:
        pytest.fail("The test invoice was not issued: see test_issues_a_test_invoice")
    return issued[0]


def test_reads_the_api_status(flashpi: Flashpi) -> None:
    assert flashpi.status.get() == {"status": "operational"}


async def test_reads_the_api_status_on_the_async_client() -> None:
    async with AsyncFlashpi(checked_key(), base_url=BASE_URL) as client:
        assert await client.status.get() == {"status": "operational"}


def test_rejects_an_invalid_invoice_with_field_errors_in_spanish(flashpi: Flashpi) -> None:
    body = sample_invoice()
    body["items"] = []
    with pytest.raises(UnprocessableEntityError) as caught:
        flashpi.invoices.create(body, language="es", max_retries=0)
    problem = caught.value
    assert problem.code == "validation_failed"
    assert len(problem.errors) > 0
    assert problem.request_id is not None
    assert re.fullmatch(r"[0-9a-f-]{36}", problem.request_id)
    assert problem.headers.get("content-language") == "es"


def test_issues_a_test_invoice_and_waits_for_the_sri(flashpi: Flashpi) -> None:
    result = flashpi.invoices.with_response.create(
        sample_invoice(), idempotency_key=IDEMPOTENCY_KEY, correlation_id="flashpi-python-live"
    )
    assert result.response.status_code in (200, 202)
    assert result.request_id
    assert result.data["type"] == "invoice"
    assert result.data["environment"] == "test"
    document = result.data

    # The SRI's test environment can be slow: follow the document for up to 2 minutes.
    for _ in range(POLLS):
        if document["status"] not in ("processing", "pending_sri"):
            break
        time.sleep(5)
        document = flashpi.documents.get(document["id"])
    assert document["status"] == "authorized"
    assert re.fullmatch(r"\d{49}", document["accessKey"])
    issued.append(document)


def test_replays_the_same_idempotency_key_instead_of_issuing_again(
    flashpi: Flashpi, invoice: Document
) -> None:
    result = flashpi.invoices.with_response.create(
        sample_invoice(), idempotency_key=IDEMPOTENCY_KEY
    )
    assert result.data["id"] == invoice["id"]
    assert result.response.headers.get("idempotent-replayed") == "true"


def test_finds_the_document_by_its_access_key(flashpi: Flashpi, invoice: Document) -> None:
    page = flashpi.documents.list({"accessKey": invoice["accessKey"], "limit": 5})
    assert [document["id"] for document in page.data] == [invoice["id"]]


def test_downloads_the_authorized_xml(flashpi: Flashpi, invoice: Document) -> None:
    xml = flashpi.documents.xml(invoice["id"])
    assert xml["kind"] == "authorized"
    assert invoice["accessKey"] in xml["xml"]


def test_downloads_the_ride_once_it_is_generated(flashpi: Flashpi, invoice: Document) -> None:
    pdf: bytes | None = None
    for _ in range(POLLS):
        try:
            pdf = flashpi.documents.pdf(invoice["id"])
            break
        except ConflictError as error:
            if error.code != "ride_not_available":
                raise
            time.sleep(5)
    assert pdf is not None
    assert pdf.startswith(b"%PDF-")


async def test_lists_the_events_of_the_document_on_the_async_client(invoice: Document) -> None:
    types: list[str] = []
    async with AsyncFlashpi(checked_key(), base_url=BASE_URL) as client:
        for poll in range(12):
            if "invoice.authorized" in types:
                break
            if poll > 0:
                await asyncio.sleep(5)
            types.clear()
            async for event in client.events.list({"documentId": invoice["id"]}):
                types.append(event["type"])
                data: Mapping[str, object] = event["data"]
                assert data.get("id") == invoice["id"]
    assert "invoice.authorized" in types


def test_answers_404_for_a_document_that_does_not_exist(flashpi: Flashpi) -> None:
    with pytest.raises(NotFoundError):
        flashpi.documents.get("01a00000-0000-7000-8000-000000000000", max_retries=0)
