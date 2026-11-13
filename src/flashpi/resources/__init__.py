"""The resources of the clients: `client.invoices`, `client.documents`, `client.issuers`...

Each one has a sync class (for `Flashpi`) and an async one (for `AsyncFlashpi`) with the same
methods, and a `with_response` view whose methods return an `APIResponse`.
"""

from .documents import (
    AsyncCreditNotes,
    AsyncDebitNotes,
    AsyncDocumentIssuer,
    AsyncDocuments,
    AsyncInvoices,
    AsyncPurchaseSettlements,
    AsyncWaybills,
    AsyncWithholdings,
    CreditNotes,
    DebitNotes,
    DocumentIssuer,
    Documents,
    Invoices,
    PurchaseSettlements,
    Waybills,
    Withholdings,
)
from .events import AsyncEvents, Events
from .issuer_onboardings import AsyncIssuerOnboardings, IssuerOnboardings
from .issuers import (
    AsyncCertificates,
    AsyncEmissionPoints,
    AsyncEstablishments,
    AsyncIssuers,
    Certificates,
    EmissionPoints,
    Establishments,
    Issuers,
)
from .status import AsyncStatusResource, StatusResource
from .webhook_endpoints import (
    AsyncWebhookDeliveries,
    AsyncWebhookEndpoints,
    WebhookDeliveries,
    WebhookEndpoints,
)

__all__ = [
    "AsyncCertificates",
    "AsyncCreditNotes",
    "AsyncDebitNotes",
    "AsyncDocumentIssuer",
    "AsyncDocuments",
    "AsyncEmissionPoints",
    "AsyncEstablishments",
    "AsyncEvents",
    "AsyncInvoices",
    "AsyncIssuerOnboardings",
    "AsyncIssuers",
    "AsyncPurchaseSettlements",
    "AsyncStatusResource",
    "AsyncWaybills",
    "AsyncWebhookDeliveries",
    "AsyncWebhookEndpoints",
    "AsyncWithholdings",
    "Certificates",
    "CreditNotes",
    "DebitNotes",
    "DocumentIssuer",
    "Documents",
    "EmissionPoints",
    "Establishments",
    "Events",
    "Invoices",
    "IssuerOnboardings",
    "Issuers",
    "PurchaseSettlements",
    "StatusResource",
    "Waybills",
    "WebhookDeliveries",
    "WebhookEndpoints",
    "Withholdings",
]
