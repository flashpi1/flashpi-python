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
from .status import AsyncStatusResource, StatusResource

__all__ = [
    "AsyncCreditNotes",
    "AsyncDebitNotes",
    "AsyncDocumentIssuer",
    "AsyncDocuments",
    "AsyncEvents",
    "AsyncInvoices",
    "AsyncPurchaseSettlements",
    "AsyncStatusResource",
    "AsyncWaybills",
    "AsyncWithholdings",
    "CreditNotes",
    "DebitNotes",
    "DocumentIssuer",
    "Documents",
    "Events",
    "Invoices",
    "PurchaseSettlements",
    "StatusResource",
    "Waybills",
    "Withholdings",
]
