"""What the README examples take from their surroundings: the client and the invoice of "Getting
started", and stand-ins for the reader's own code.

scripts/readme.py imports from here exactly the names each example uses without defining them.
Like the examples, this module is only type-checked, never run.
"""

from flashpi import Flashpi
from flashpi.types import CreateInvoice, Document, WebhookEvent


class Order:
    """An order of the reader's shop."""

    id: str


flashpi: Flashpi
"""The client of "Getting started"."""

invoice: Document
"""The invoice issued in "Getting started"."""

body: CreateInvoice
"""An invoice to issue."""

order: Order
"""The order an invoice is issued for."""

document_id: str
"""The id of a document."""


def save_for_retry(body: CreateInvoice, idempotency_key: str) -> None:
    """The reader's retry queue."""


def handle_event(event: WebhookEvent) -> None:
    """The reader's handling of a webhook event, like the branches of the Django example."""
