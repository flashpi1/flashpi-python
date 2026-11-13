"""Public types.

The resource types come from the API's OpenAPI document (`_generated.py`); the ones below are
written by hand where the SDK adds something: shorter names, the webhook bodies, the open error
code unions, list filters, uploads and the XML of a document.

Models are TypedDicts: plain dicts at runtime, with the keys of the API (camelCase).
"""

from typing import IO, Literal, NotRequired, TypeAlias, TypedDict

from ._generated import (
    AccountEmailSending,
    AccountEmailSendingWindow,
    AccountEvent,
    AccountEventType,
    Certificate,
    CertificateEvent,
    CertificateEventType,
    CertificateRejection,
    CertificateRevocation,
    CertificatesListQuery,
    CompletedIssuerOnboarding,
    CompleteIssuerOnboarding,
    CreateCreditNote,
    CreateDebitNote,
    CreateEmissionPoint,
    CreateEstablishment,
    CreateInvoice,
    CreateIssuer,
    CreatePurchaseSettlement,
    CreateWaybill,
    CreateWebhookEndpoint,
    CreateWithholding,
    DebitNoteReason,
    Document,
    DocumentAuthorization,
    DocumentCounterparty,
    DocumentEmail,
    DocumentEmailDelivery,
    DocumentEmailWarning,
    DocumentEnvironment,
    DocumentEvent,
    DocumentEventType,
    DocumentFailure,
    DocumentItem,
    DocumentOptions,
    DocumentParty,
    DocumentPayment,
    DocumentRide,
    DocumentsListQuery,
    DocumentSriMessage,
    DocumentStatus,
    DocumentTax,
    DocumentTaxTotal,
    DocumentTotals,
    DocumentType,
    EmissionPoint,
    EmissionPointsListQuery,
    ErrorCode,
    Establishment,
    EstablishmentsListQuery,
    Event,
    EventsListQuery,
    EventThin,
    FieldErrorCode,
    Issuer,
    IssuerBranding,
    IssuerBrandingInput,
    IssuerOnboarding,
    IssuerOnboardingCertificate,
    IssuerOnboardingCompletion,
    IssuerOnboardingExistingIssuer,
    IssuerOnboardingHolder,
    IssuerOnboardingIdentification,
    IssuerOnboardingIssuingCa,
    IssuerOnboardingPrefill,
    IssuerOnboardingPrefillTaxProfile,
    IssuerOnboardingRejection,
    IssuerOnboardingSri,
    IssuerOnboardingSriProfile,
    IssuersListQuery,
    IssuerTaxProfile,
    IssuerTaxProfileInput,
    IssuerTaxProfilePatch,
    ModifiedDocument,
    Pagination,
    ProblemDetails,
    RotateWebhookEndpointSecret,
    SendDocumentEmail,
    Status,
    SupportingDocument,
    SupportingDocumentTax,
    UpdateEstablishment,
    UpdateIssuer,
    UpdateWebhookEndpoint,
    WaybillCarrier,
    WaybillItem,
    WaybillRecipient,
    WaybillSupportingDocument,
    WebhookDelivery,
    WebhookDeliveryAttempt,
    WebhookDeliveryDetail,
    WebhookEndpoint,
    WebhookEndpointsDeliveriesListQuery,
    WebhookEndpointSecret,
    WebhookEndpointsListQuery,
    WebhookEndpointVerification,
    WebhookEndpointVerificationEvent,
    WebhookEndpointVerificationEventData,
    WithheldSubject,
    Withholding,
    WithholdingBananaBoxes,
    WithholdingDividends,
    WithholdingForeignPayment,
    WithholdingPayment,
)

Language: TypeAlias = Literal["en", "es"]
"""Languages the API writes its messages in. Error codes are the same in both."""

Environment: TypeAlias = DocumentEnvironment
"""`test` (SRI pruebas, fp_test_ keys) or `live` (SRI production, fp_live_ keys)."""

ThinEvent: TypeAlias = EventThin
"""The body of a webhook endpoint in thin mode: the event without `data`."""

EventType: TypeAlias = DocumentEventType | CertificateEventType | AccountEventType
"""Every event type the API sends today. New types may appear: keep a default branch."""

WebhookEvent: TypeAlias = Event | WebhookEndpointVerificationEvent
"""What a webhook endpoint in full mode receives: an event, or the activation handshake
(`webhook_endpoint.verification`), which must be answered with `{"challenge": data["challenge"]}`.
Narrow it on `event["type"]`."""

ThinWebhookEvent: TypeAlias = ThinEvent | WebhookEndpointVerificationEvent
"""What a webhook endpoint in thin mode receives."""

ApiErrorCode: TypeAlias = ErrorCode | str
"""An error code of the API (`code` of the Problem Details). New codes can appear before this
package knows them, so any string is accepted."""

ApiFieldErrorCode: TypeAlias = FieldErrorCode | str
"""A field error code (`errors[].code`, such as `required` or `invalid_check_digit`). The list is
open: new codes can appear before this package knows them, so any string is accepted."""

Problem: TypeAlias = ProblemDetails
"""The Problem Details body of an API error (RFC 9457), with the extension members some codes add
(`documentId`, `limit`, `resetsAt`, `rideStatus`, `expectedTotal`, ...); others may appear."""


class FieldError(TypedDict):
    """A field-level problem of a request: the field's path, its code and a localized message."""

    field: str
    """Path of the field, such as `items[0].quantity`."""

    code: ApiFieldErrorCode
    """Stable machine-readable code of the problem."""

    message: str
    """Localized explanation."""


DocumentListParams: TypeAlias = DocumentsListQuery
"""Filters of `documents.list()`."""

EventListParams: TypeAlias = EventsListQuery
"""Filters of `events.list()`."""

WebhookDeliveryListParams: TypeAlias = WebhookEndpointsDeliveriesListQuery
"""Filters of `webhook_endpoints.deliveries.list()`."""

IssuerListParams: TypeAlias = IssuersListQuery
"""Paging of `issuers.list()`."""

EstablishmentListParams: TypeAlias = EstablishmentsListQuery
"""Paging of `issuers.establishments.list()`."""

EmissionPointListParams: TypeAlias = EmissionPointsListQuery
"""Paging of `issuers.establishments.emission_points.list()`."""

CertificateListParams: TypeAlias = CertificatesListQuery
"""Paging of `issuers.certificates.list()`."""

WebhookEndpointListParams: TypeAlias = WebhookEndpointsListQuery
"""Paging of `webhook_endpoints.list()`."""


class CertificateUpload(TypedDict):
    """A .p12 certificate file and its password, for `issuers.certificates.upload()` and
    `issuer_onboardings.create()`."""

    file: bytes | bytearray | memoryview | IO[bytes]
    """The .p12 (PKCS #12) file, up to 1 MiB: its bytes or a file opened in binary mode."""

    password: str
    """The certificate's password (sent to Flashpi only, never stored in plain text)."""

    filename: NotRequired[str]
    """File name sent with the upload (default `certificate.p12`)."""


DocumentXmlKind: TypeAlias = Literal["authorized", "signed", "unsigned"]
"""Which stage an XML comes from. Only `authorized` is the valid tax document."""


class DocumentXml(TypedDict):
    """The XML of a document and which stage it comes from."""

    xml: str
    """The XML text."""

    kind: DocumentXmlKind | None
    """`authorized` (the SRI's authorization with the document inside), `signed` (sent, not yet
    authorized) or `unsigned` (before signing); None when the API did not say."""


__all__ = [
    "AccountEmailSending",
    "AccountEmailSendingWindow",
    "AccountEvent",
    "AccountEventType",
    "ApiErrorCode",
    "ApiFieldErrorCode",
    "Certificate",
    "CertificateEvent",
    "CertificateEventType",
    "CertificateListParams",
    "CertificateRejection",
    "CertificateRevocation",
    "CertificateUpload",
    "CompleteIssuerOnboarding",
    "CompletedIssuerOnboarding",
    "CreateCreditNote",
    "CreateDebitNote",
    "CreateEmissionPoint",
    "CreateEstablishment",
    "CreateInvoice",
    "CreateIssuer",
    "CreatePurchaseSettlement",
    "CreateWaybill",
    "CreateWebhookEndpoint",
    "CreateWithholding",
    "DebitNoteReason",
    "Document",
    "DocumentAuthorization",
    "DocumentCounterparty",
    "DocumentEmail",
    "DocumentEmailDelivery",
    "DocumentEmailWarning",
    "DocumentEvent",
    "DocumentEventType",
    "DocumentFailure",
    "DocumentItem",
    "DocumentListParams",
    "DocumentOptions",
    "DocumentParty",
    "DocumentPayment",
    "DocumentRide",
    "DocumentSriMessage",
    "DocumentStatus",
    "DocumentTax",
    "DocumentTaxTotal",
    "DocumentTotals",
    "DocumentType",
    "DocumentXml",
    "DocumentXmlKind",
    "EmissionPoint",
    "EmissionPointListParams",
    "Environment",
    "ErrorCode",
    "Establishment",
    "EstablishmentListParams",
    "Event",
    "EventListParams",
    "EventThin",
    "EventType",
    "FieldError",
    "FieldErrorCode",
    "Issuer",
    "IssuerBranding",
    "IssuerBrandingInput",
    "IssuerListParams",
    "IssuerOnboarding",
    "IssuerOnboardingCertificate",
    "IssuerOnboardingCompletion",
    "IssuerOnboardingExistingIssuer",
    "IssuerOnboardingHolder",
    "IssuerOnboardingIdentification",
    "IssuerOnboardingIssuingCa",
    "IssuerOnboardingPrefill",
    "IssuerOnboardingPrefillTaxProfile",
    "IssuerOnboardingRejection",
    "IssuerOnboardingSri",
    "IssuerOnboardingSriProfile",
    "IssuerTaxProfile",
    "IssuerTaxProfileInput",
    "IssuerTaxProfilePatch",
    "Language",
    "ModifiedDocument",
    "Pagination",
    "Problem",
    "ProblemDetails",
    "RotateWebhookEndpointSecret",
    "SendDocumentEmail",
    "Status",
    "SupportingDocument",
    "SupportingDocumentTax",
    "ThinEvent",
    "ThinWebhookEvent",
    "UpdateEstablishment",
    "UpdateIssuer",
    "UpdateWebhookEndpoint",
    "WaybillCarrier",
    "WaybillItem",
    "WaybillRecipient",
    "WaybillSupportingDocument",
    "WebhookDelivery",
    "WebhookDeliveryAttempt",
    "WebhookDeliveryDetail",
    "WebhookDeliveryListParams",
    "WebhookEndpoint",
    "WebhookEndpointListParams",
    "WebhookEndpointSecret",
    "WebhookEndpointVerification",
    "WebhookEndpointVerificationEvent",
    "WebhookEndpointVerificationEventData",
    "WebhookEvent",
    "WithheldSubject",
    "Withholding",
    "WithholdingBananaBoxes",
    "WithholdingDividends",
    "WithholdingForeignPayment",
    "WithholdingPayment",
]
