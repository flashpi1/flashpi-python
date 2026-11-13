"""Issuing the six document types, and every issued document: search, XML, RIDE (PDF) and
email."""

from collections.abc import Mapping
from functools import cached_property
from typing import Any, ClassVar, Generic, TypeVar, Unpack, cast

from flashpi._http import RequestOptions, RequestSpec, path_of
from flashpi._pagination import AsyncPaginator, ListBody, Page
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import APIResponse, async_response_wrapper, response_wrapper
from flashpi.types import (
    CreateCreditNote,
    CreateDebitNote,
    CreateInvoice,
    CreatePurchaseSettlement,
    CreateWaybill,
    CreateWithholding,
    Document,
    DocumentListParams,
    DocumentXml,
    DocumentXmlKind,
)

BodyT = TypeVar("BodyT", bound=Mapping[str, Any])

DEFAULT_WAIT_SECONDS = 15
"""Seconds the API waits for the SRI in sync mode when `waitTimeoutSeconds` is not sent."""

SYNC_MARGIN_SECONDS = 15
"""Time on top of the sync wait for Flashpi to build, sign and answer."""

XML_ACCEPT = "application/xml, application/problem+json"
PDF_ACCEPT = "application/pdf, application/problem+json"


def sync_timeout_floor(body: object) -> float:
    """The shortest per-attempt timeout for issuing `body`, in seconds.

    In sync mode (`options.waitForAuthorization`) the API holds the request for up to
    `waitTimeoutSeconds` (15 by default) while the SRI decides, so each attempt waits at least
    that plus 15 seconds. Otherwise 0: the client's timeout applies.
    """
    settings = _members(_members(body).get("options"))
    if settings.get("waitForAuthorization") is not True:
        return 0
    wait = settings.get("waitTimeoutSeconds")
    if isinstance(wait, bool) or not isinstance(wait, int | float):
        wait = DEFAULT_WAIT_SECONDS
    return wait + SYNC_MARGIN_SECONDS


def _members(value: object) -> Mapping[str, object]:
    """The members of a dict, or none for anything else."""
    return cast("Mapping[str, object]", value) if isinstance(value, Mapping) else {}


def issue_spec(path: str, body: object, options: RequestOptions) -> RequestSpec[Document]:
    """The POST that issues a document.

    Its retries reuse the same Idempotency-Key, and when a retry finds the document already
    created by an earlier attempt (422 `idempotency_key_reused` with a `documentId`), the call
    returns that document instead of an error.
    """
    return RequestSpec[Document](
        method="POST",
        path=path,
        body=body,
        options=options,
        min_timeout=sync_timeout_floor(body),
        recover_document=True,
    )


def list_spec(
    params: DocumentListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[Document]]:
    return RequestSpec[ListBody[Document]](
        method="GET", path="/v1/documents", query=params, options=options
    )


def get_spec(document_id: str, options: RequestOptions) -> RequestSpec[Document]:
    path = path_of("/v1/documents/{}", document_id)
    return RequestSpec[Document](method="GET", path=path, options=options)


def xml_spec(document_id: str, options: RequestOptions) -> RequestSpec[str]:
    path = path_of("/v1/documents/{}/xml", document_id)
    return RequestSpec[str](
        method="GET", path=path, accept=XML_ACCEPT, response_type="text", options=options
    )


def pdf_spec(document_id: str, options: RequestOptions) -> RequestSpec[bytes]:
    path = path_of("/v1/documents/{}/pdf", document_id)
    return RequestSpec[bytes](
        method="GET", path=path, accept=PDF_ACCEPT, response_type="bytes", options=options
    )


def send_email_spec(document_id: str, options: RequestOptions) -> RequestSpec[Document]:
    path = path_of("/v1/documents/{}/email", document_id)
    return RequestSpec[Document](method="POST", path=path, body={}, options=options)


def document_xml(result: APIResponse[str]) -> DocumentXml:
    """The XML of an answer and its stage, from the Flashpi-Xml-Kind header."""
    kind = result.response.headers.get("flashpi-xml-kind")
    known: tuple[DocumentXmlKind, ...] = ("authorized", "signed", "unsigned")
    return {"xml": result.data, "kind": next((value for value in known if value == kind), None)}


# Flashpi


class DocumentIssuer(SyncAPIResource, Generic[BodyT]):
    """Issues one document type. The answer is the document: `processing` right away (202), or,
    with `options.waitForAuthorization`, its outcome once the SRI decides (200), unless the wait
    ends first (202 with `processing` or `pending_sri`; follow it with webhooks or
    `documents.get()`)."""

    _path: ClassVar[str]

    def create(self, body: BodyT, **options: Unpack[RequestOptions]) -> Document:
        """Issues the document. Retries reuse the same Idempotency-Key, and when a retry finds
        the document already created, its current state is returned instead of an error."""
        return self._request(issue_spec(self._path, body, options))

    @cached_property
    def with_response(self) -> "DocumentIssuerWithResponse[BodyT]":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return DocumentIssuerWithResponse(self)


class DocumentIssuerWithResponse(Generic[BodyT]):
    def __init__(self, issuer: DocumentIssuer[BodyT]) -> None:
        self.create = response_wrapper(issuer.create)


class Invoices(DocumentIssuer[CreateInvoice]):
    """Invoices (facturas)."""

    _path = "/v1/invoices"


class CreditNotes(DocumentIssuer[CreateCreditNote]):
    """Credit notes (notas de crédito)."""

    _path = "/v1/credit-notes"


class DebitNotes(DocumentIssuer[CreateDebitNote]):
    """Debit notes (notas de débito)."""

    _path = "/v1/debit-notes"


class PurchaseSettlements(DocumentIssuer[CreatePurchaseSettlement]):
    """Purchase settlements (liquidaciones de compra)."""

    _path = "/v1/purchase-settlements"


class Waybills(DocumentIssuer[CreateWaybill]):
    """Waybills (guías de remisión)."""

    _path = "/v1/waybills"


class Withholdings(DocumentIssuer[CreateWithholding]):
    """Withholding receipts (comprobantes de retención)."""

    _path = "/v1/withholdings"


class Documents(SyncAPIResource):
    """Every issued document, of any type: search, XML, RIDE (PDF) and email."""

    def list(
        self, params: DocumentListParams | None = None, **options: Unpack[RequestOptions]
    ) -> Page[Document]:
        """Lists documents, newest first, with optional filters."""
        return self._list(list_spec(params, options))

    def get(self, document_id: str, **options: Unpack[RequestOptions]) -> Document:
        """Retrieves a document with its tax status, SRI messages, RIDE and email state."""
        return self._request(get_spec(document_id, options))

    def xml(self, document_id: str, **options: Unpack[RequestOptions]) -> DocumentXml:
        """The document's XML: the authorized one once the SRI authorizes it, otherwise the
        signed or unsigned one (see `kind`)."""
        return document_xml(self._call(xml_spec(document_id, options)))

    def pdf(self, document_id: str, **options: Unpack[RequestOptions]) -> bytes:
        """The RIDE (the printable PDF) of an authorized document. Raises a ConflictError with
        code `ride_not_available` while it is still being generated."""
        return self._request(pdf_spec(document_id, options))

    def send_email(self, document_id: str, **options: Unpack[RequestOptions]) -> Document:
        """Emails the authorized document (RIDE and XML) again to the address of its request.
        The new delivery shows in `email.deliveries`; daily limits apply (RateLimitError)."""
        return self._request(send_email_spec(document_id, options))

    @cached_property
    def with_response(self) -> "DocumentsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return DocumentsWithResponse(self)


class DocumentsWithResponse:
    def __init__(self, documents: Documents) -> None:
        self.list = response_wrapper(documents.list)
        self.get = response_wrapper(documents.get)
        self.xml = response_wrapper(documents.xml)
        self.pdf = response_wrapper(documents.pdf)
        self.send_email = response_wrapper(documents.send_email)


# AsyncFlashpi


class AsyncDocumentIssuer(AsyncAPIResource, Generic[BodyT]):
    """Issues one document type, for `AsyncFlashpi`. See `DocumentIssuer`."""

    _path: ClassVar[str]

    async def create(self, body: BodyT, **options: Unpack[RequestOptions]) -> Document:
        """Issues the document. Retries reuse the same Idempotency-Key, and when a retry finds
        the document already created, its current state is returned instead of an error."""
        return await self._request(issue_spec(self._path, body, options))

    @cached_property
    def with_response(self) -> "AsyncDocumentIssuerWithResponse[BodyT]":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncDocumentIssuerWithResponse(self)


class AsyncDocumentIssuerWithResponse(Generic[BodyT]):
    def __init__(self, issuer: AsyncDocumentIssuer[BodyT]) -> None:
        self.create = async_response_wrapper(issuer.create)


class AsyncInvoices(AsyncDocumentIssuer[CreateInvoice]):
    """Invoices (facturas)."""

    _path = "/v1/invoices"


class AsyncCreditNotes(AsyncDocumentIssuer[CreateCreditNote]):
    """Credit notes (notas de crédito)."""

    _path = "/v1/credit-notes"


class AsyncDebitNotes(AsyncDocumentIssuer[CreateDebitNote]):
    """Debit notes (notas de débito)."""

    _path = "/v1/debit-notes"


class AsyncPurchaseSettlements(AsyncDocumentIssuer[CreatePurchaseSettlement]):
    """Purchase settlements (liquidaciones de compra)."""

    _path = "/v1/purchase-settlements"


class AsyncWaybills(AsyncDocumentIssuer[CreateWaybill]):
    """Waybills (guías de remisión)."""

    _path = "/v1/waybills"


class AsyncWithholdings(AsyncDocumentIssuer[CreateWithholding]):
    """Withholding receipts (comprobantes de retención)."""

    _path = "/v1/withholdings"


class AsyncDocuments(AsyncAPIResource):
    """Every issued document, of any type: search, XML, RIDE (PDF) and email."""

    def list(
        self, params: DocumentListParams | None = None, **options: Unpack[RequestOptions]
    ) -> AsyncPaginator[Document]:
        """Lists documents, newest first, with optional filters."""
        return self._list(list_spec(params, options))

    async def get(self, document_id: str, **options: Unpack[RequestOptions]) -> Document:
        """Retrieves a document with its tax status, SRI messages, RIDE and email state."""
        return await self._request(get_spec(document_id, options))

    async def xml(self, document_id: str, **options: Unpack[RequestOptions]) -> DocumentXml:
        """The document's XML: the authorized one once the SRI authorizes it, otherwise the
        signed or unsigned one (see `kind`)."""
        return document_xml(await self._call(xml_spec(document_id, options)))

    async def pdf(self, document_id: str, **options: Unpack[RequestOptions]) -> bytes:
        """The RIDE (the printable PDF) of an authorized document. Raises a ConflictError with
        code `ride_not_available` while it is still being generated."""
        return await self._request(pdf_spec(document_id, options))

    async def send_email(self, document_id: str, **options: Unpack[RequestOptions]) -> Document:
        """Emails the authorized document (RIDE and XML) again to the address of its request.
        The new delivery shows in `email.deliveries`; daily limits apply (RateLimitError)."""
        return await self._request(send_email_spec(document_id, options))

    @cached_property
    def with_response(self) -> "AsyncDocumentsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncDocumentsWithResponse(self)


class AsyncDocumentsWithResponse:
    def __init__(self, documents: AsyncDocuments) -> None:
        self.list = async_response_wrapper(documents.list)
        self.get = async_response_wrapper(documents.get)
        self.xml = async_response_wrapper(documents.xml)
        self.pdf = async_response_wrapper(documents.pdf)
        self.send_email = async_response_wrapper(documents.send_email)
