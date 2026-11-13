"""The Flashpi clients: `Flashpi` (sync) and `AsyncFlashpi` (asyncio), with the same API."""

import os
import re
from collections.abc import Mapping
from types import TracebackType
from typing import Self, cast

import httpx

from ._errors import FlashpiError
from ._http import AsyncEngine, ClientConfig, SyncEngine
from ._validate import checked_headers, header_value, valid_retries, valid_timeout
from ._webhooks import Webhooks
from .resources.documents import (
    AsyncCreditNotes,
    AsyncDebitNotes,
    AsyncDocuments,
    AsyncInvoices,
    AsyncPurchaseSettlements,
    AsyncWaybills,
    AsyncWithholdings,
    CreditNotes,
    DebitNotes,
    Documents,
    Invoices,
    PurchaseSettlements,
    Waybills,
    Withholdings,
)
from .resources.events import AsyncEvents, Events
from .resources.issuer_onboardings import AsyncIssuerOnboardings, IssuerOnboardings
from .resources.issuers import AsyncIssuers, Issuers
from .resources.status import AsyncStatusResource, StatusResource
from .resources.webhook_endpoints import AsyncWebhookEndpoints, WebhookEndpoints
from .types import Environment, Language

DEFAULT_BASE_URL = "https://api.flashpi.com.ec"
DEFAULT_TIMEOUT = 60.0
"""Seconds each attempt of a request may take, from sending it to reading the whole answer (the
Node SDK's 60 000 ms)."""
DEFAULT_MAX_RETRIES = 2

_API_KEY_CHARACTERS = re.compile(r"[\x21-\x7e]+")
"""What an API key is made of: visible ASCII, without spaces."""
_JS_SPACE = r"[\t\n\v\f\r \xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
_AROUND = re.compile(rf"\A{_JS_SPACE}+|{_JS_SPACE}+\Z")
"""What JavaScript's `trim()` removes around a string, the Node SDK's key included: its white
space and line breaks, and the byte order mark (U+FEFF) that `str.strip()` keeps."""


def _configure(
    api_key: str | None,
    *,
    base_url: str | None,
    timeout: float | None,
    max_retries: int | None,
    language: Language | None,
    default_headers: Mapping[str, str] | None,
) -> tuple[ClientConfig, Environment]:
    # The key is checked first, so a missing or bad key is the error reported, then read again
    # once every other setting is checked: no local of this frame keeps it, since error trackers
    # record the local variables of the frames an error passes through (and scrub `api_key` by
    # name at best).
    _api_key(api_key)
    headers = checked_headers("default_headers", default_headers)
    if language is not None:
        language = cast("Language", header_value("language", language))
    if any(name.lower() == "idempotency-key" for name in headers):
        raise FlashpiError(
            "default_headers cannot carry an Idempotency-Key: it must be unique per operation. "
            "Pass idempotency_key= to each create() instead"
        )
    url = DEFAULT_BASE_URL if base_url is None else base_url
    if not _is_http_url(url):
        raise FlashpiError(f"base_url must be an http:// or https:// URL, got {url!r}")
    seconds = valid_timeout("timeout", DEFAULT_TIMEOUT if timeout is None else timeout)
    retries = valid_retries(
        "max_retries", DEFAULT_MAX_RETRIES if max_retries is None else max_retries
    )
    config = ClientConfig(
        api_key=_api_key(api_key),
        base_url=url,
        timeout=seconds,
        max_retries=retries,
        language=language,
        default_headers=headers,
    )
    return config, "test" if config.api_key.startswith("fp_test_") else "live"


def _is_http_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = httpx.URL(url)
    except httpx.InvalidURL:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.host)


def _api_key(api_key: str | None) -> str:
    """The key: the argument or FLASHPI_API_KEY, trimmed as JavaScript's `trim()`, the byte order
    mark included. A key that cannot be used raises FlashpiError, with no local keeping it."""
    value: object = os.environ.get("FLASHPI_API_KEY") if api_key is None else api_key
    key = _AROUND.sub("", value) if isinstance(value, str) else ""
    problem = _key_problem(key)
    if problem is None:
        return key
    del value, key
    raise FlashpiError(problem)


def _key_problem(key: str) -> str | None:
    """Why a trimmed key cannot be used, or None. It returns instead of raising, so its frame is
    never part of an error."""
    if not key:
        return (
            "Missing API key: pass it to Flashpi(api_key=...) or set the FLASHPI_API_KEY "
            "environment variable"
        )
    if key.startswith("whsec_"):
        return (
            "That is a webhook signing secret (whsec_...), not an API key: use it with "
            "flashpi.webhooks"
        )
    if not key.startswith(("fp_test_", "fp_live_")):
        return "The API key must start with fp_test_ or fp_live_"
    if not _API_KEY_CHARACTERS.fullmatch(key):
        # Never the key: httpx would refuse it in the Authorization header and quote it.
        return (
            "The API key has spaces, line breaks or other characters an API key cannot have: "
            "copy it again from the Flashpi console"
        )
    return None


def _describe(client: object, environment: Environment, config: ClientConfig) -> str:
    # Never the API key.
    return f"{type(client).__name__}(environment={environment!r}, base_url={config.base_url!r})"


class Flashpi:
    """The Flashpi API client.

    ```python
    from flashpi import Flashpi

    with Flashpi() as flashpi:  # reads FLASHPI_API_KEY
        invoice = flashpi.invoices.create({...})
    ```

    An `fp_test_` key issues in the SRI test environment (pruebas); an `fp_live_` key issues real
    documents in production. Use it on servers only: the key must stay secret.
    """

    environment: Environment
    """`test` for fp_test_ keys (SRI pruebas), `live` for fp_live_ keys (SRI production)."""

    invoices: Invoices
    """Invoices (facturas)."""

    credit_notes: CreditNotes
    """Credit notes (notas de crédito)."""

    debit_notes: DebitNotes
    """Debit notes (notas de débito)."""

    purchase_settlements: PurchaseSettlements
    """Purchase settlements (liquidaciones de compra)."""

    waybills: Waybills
    """Waybills (guías de remisión)."""

    withholdings: Withholdings
    """Withholding receipts (comprobantes de retención)."""

    documents: Documents
    """Every issued document: search, XML, RIDE (PDF) and email."""

    issuers: Issuers
    """Issuers (RUCs) with their establishments, emission points and certificates."""

    issuer_onboardings: IssuerOnboardings
    """Create an issuer from its .p12 certificate."""

    webhook_endpoints: WebhookEndpoints
    """The URLs Flashpi sends events to."""

    events: Events
    """Events of documents, certificates and email sending."""

    status: StatusResource
    """The API's status."""

    webhooks: Webhooks
    """Verify the signature of the webhooks you receive (no API key needed)."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        language: Language | None = None,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Creates a client.

        Args:
            api_key: The API key (`fp_test_...` or `fp_live_...`). Defaults to the
                FLASHPI_API_KEY environment variable.
            base_url: The API's address (default https://api.flashpi.com.ec).
            timeout: Seconds each attempt of a request may take, from sending it to reading the
                whole answer (default 60). Issuing with `options.waitForAuthorization` raises it,
                on both clients, to the wait plus 15 seconds. On `Flashpi` the deadline is
                checked as the answer arrives, so one stalled read can add up to one timeout.
            max_retries: Retries after network errors, timeouts, 429 and 5xx (default 2; 0 turns
                them off).
            language: Language of the API's messages: `en` (default) or `es`. Error codes do not
                change.
            default_headers: Headers sent with every request (not `Idempotency-Key`: that one is
                per request).
            http_client: An `httpx.Client` to send the requests with (proxies, tests). The SDK
                never follows redirects, and leaves closing this client to you. A body that this
                client's own response hooks read is checked against the deadline only once it
                has been read.
        """
        config, self.environment = _configure(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            language=language,
            default_headers=default_headers,
        )
        if http_client is not None and not isinstance(cast("object", http_client), httpx.Client):
            raise TypeError(
                "http_client must be an httpx.Client (AsyncFlashpi takes an httpx.AsyncClient)"
            )
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.Client(follow_redirects=False)
        self._engine = SyncEngine(config, self._http_client)
        self.invoices = Invoices(self._engine)
        self.credit_notes = CreditNotes(self._engine)
        self.debit_notes = DebitNotes(self._engine)
        self.purchase_settlements = PurchaseSettlements(self._engine)
        self.waybills = Waybills(self._engine)
        self.withholdings = Withholdings(self._engine)
        self.documents = Documents(self._engine)
        self.issuers = Issuers(self._engine)
        self.issuer_onboardings = IssuerOnboardings(self._engine)
        self.webhook_endpoints = WebhookEndpoints(self._engine)
        self.events = Events(self._engine)
        self.status = StatusResource(self._engine)
        self.webhooks = Webhooks()

    def close(self) -> None:
        """Closes the connections, unless the http_client came from you."""
        if self._owns_http_client:
            self._http_client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return _describe(self, self.environment, self._engine.config)


class AsyncFlashpi:
    """The Flashpi API client for asyncio, with the same API as `Flashpi`.

    ```python
    from flashpi import AsyncFlashpi

    async with AsyncFlashpi() as flashpi:  # reads FLASHPI_API_KEY
        invoice = await flashpi.invoices.create({...})
    ```

    An `fp_test_` key issues in the SRI test environment (pruebas); an `fp_live_` key issues real
    documents in production. Use it on servers only: the key must stay secret.
    """

    environment: Environment
    """`test` for fp_test_ keys (SRI pruebas), `live` for fp_live_ keys (SRI production)."""

    invoices: AsyncInvoices
    """Invoices (facturas)."""

    credit_notes: AsyncCreditNotes
    """Credit notes (notas de crédito)."""

    debit_notes: AsyncDebitNotes
    """Debit notes (notas de débito)."""

    purchase_settlements: AsyncPurchaseSettlements
    """Purchase settlements (liquidaciones de compra)."""

    waybills: AsyncWaybills
    """Waybills (guías de remisión)."""

    withholdings: AsyncWithholdings
    """Withholding receipts (comprobantes de retención)."""

    documents: AsyncDocuments
    """Every issued document: search, XML, RIDE (PDF) and email."""

    issuers: AsyncIssuers
    """Issuers (RUCs) with their establishments, emission points and certificates."""

    issuer_onboardings: AsyncIssuerOnboardings
    """Create an issuer from its .p12 certificate."""

    webhook_endpoints: AsyncWebhookEndpoints
    """The URLs Flashpi sends events to."""

    events: AsyncEvents
    """Events of documents, certificates and email sending."""

    status: AsyncStatusResource
    """The API's status."""

    webhooks: Webhooks
    """Verify the signature of the webhooks you receive (no API key needed)."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        language: Language | None = None,
        default_headers: Mapping[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        """Creates a client. The arguments are the ones of `Flashpi`, with an
        `httpx.AsyncClient` as `http_client`."""
        config, self.environment = _configure(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            language=language,
            default_headers=default_headers,
        )
        if http_client is not None and not isinstance(
            cast("object", http_client), httpx.AsyncClient
        ):
            raise TypeError(
                "http_client must be an httpx.AsyncClient (Flashpi takes an httpx.Client)"
            )
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(follow_redirects=False)
        self._engine = AsyncEngine(config, self._http_client)
        self.invoices = AsyncInvoices(self._engine)
        self.credit_notes = AsyncCreditNotes(self._engine)
        self.debit_notes = AsyncDebitNotes(self._engine)
        self.purchase_settlements = AsyncPurchaseSettlements(self._engine)
        self.waybills = AsyncWaybills(self._engine)
        self.withholdings = AsyncWithholdings(self._engine)
        self.documents = AsyncDocuments(self._engine)
        self.issuers = AsyncIssuers(self._engine)
        self.issuer_onboardings = AsyncIssuerOnboardings(self._engine)
        self.webhook_endpoints = AsyncWebhookEndpoints(self._engine)
        self.events = AsyncEvents(self._engine)
        self.status = AsyncStatusResource(self._engine)
        self.webhooks = Webhooks()

    async def aclose(self) -> None:
        """Closes the connections, unless the http_client came from you."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return _describe(self, self.environment, self._engine.config)
