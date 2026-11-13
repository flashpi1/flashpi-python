"""The resources of the clients: `client.invoices`, `client.documents`, `client.issuers`...

Each one has a sync class (for `Flashpi`) and an async one (for `AsyncFlashpi`) with the same
methods, and a `with_response` view whose methods return an `APIResponse`.
"""

from .events import AsyncEvents, Events
from .status import AsyncStatusResource, StatusResource

__all__ = [
    "AsyncEvents",
    "AsyncStatusResource",
    "Events",
    "StatusResource",
]
