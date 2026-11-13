# Flashpi for Python

The official Python SDK for [Flashpi](https://flashpi.com.ec), the electronic invoicing API for
Ecuador's SRI.

[Español](https://github.com/flashpi1/flashpi-python/blob/main/README.md)

- The 45 operations of the API: the six document types, documents (XML, RIDE PDF, email),
  issuers with establishments, emission points and .p12 certificates, webhooks and events.
- A sync client (`Flashpi`) and an async one (`AsyncFlashpi`, asyncio) with the same methods.
- Types (`TypedDict`) generated from the API's OpenAPI document, so your editor and type checker
  know every field.
- Safe retries: every issuing request carries an `Idempotency-Key`, so a retry never issues a
  document twice.
- Typed errors (RFC 9457) with their `code`, field errors and `request_id`.
- Automatic pagination with `for` and `async for`.
- Webhook signature verification (Standard Webhooks) for Django, Flask, FastAPI or any framework.
- Python 3.11 or later. One dependency: [httpx](https://www.python-httpx.org/).

## Install

```bash
pip install flashpi
```

Or `uv add flashpi`, `poetry add flashpi`.

## Getting started

Create an API key in the [console](https://flashpi.com.ec/app/) and keep it in the
`FLASHPI_API_KEY` environment variable. An `fp_test_` key issues in the SRI's test environment;
an `fp_live_` key issues real documents in production.

```python
from flashpi import Flashpi

# Reads FLASHPI_API_KEY; you can also pass it: Flashpi("fp_test_...")
flashpi = Flashpi()

invoice = flashpi.invoices.create(
    {
        "issuerId": "<the demo issuer id or yours>",
        "establishment": "001",
        "emissionPoint": "001",
        "customer": {
            "idType": "ruc",
            "id": "1760013210001",
            "name": "PRUEBAS SERVICIO DE RENTAS INTERNAS",
            "address": "Av. Amazonas y Villalengua, Quito",
        },
        "items": [
            {
                "code": "P-001",
                "description": "Test service",
                "quantity": "1",
                "unitPrice": "1.00",
                "taxes": [{"type": "vat", "rate": "15"}],
            }
        ],
        "payments": [{"method": "cash", "amount": "1.15"}],
        "options": {"waitForAuthorization": True},
    }
)

print(invoice["status"], invoice["accessKey"])
```

Requests and answers are dictionaries with the API's own keys, in camelCase
(`invoice["accessKey"]`), typed with the `TypedDict`s of `flashpi.types`
(`from flashpi.types import CreateInvoice, Document`). Amounts and quantities are **strings**
(`"1.15"`), never numbers, so no decimals are lost.

With the **demo issuer** you can issue test documents without uploading a certificate: its id is
on the console's Overview (up to 50 documents a day). See
[Sandbox and demo issuer](https://flashpi.com.ec/docs/en/sandbox/).

A client keeps a pool of connections: create one and reuse it. Close it with `flashpi.close()`,
or use it in a `with` block.

## Async

`AsyncFlashpi` has the same resources and methods; await them.

```python
import asyncio

from flashpi import AsyncFlashpi


async def main() -> None:
    async with AsyncFlashpi() as flashpi:
        status = await flashpi.status.get()
        print(status["status"])

        async for document in flashpi.documents.list({"status": "authorized"}):
            print(document["accessKey"])


asyncio.run(main())
```

It runs on asyncio. To cancel a call, cancel its task (for example with `asyncio.timeout()`).
Without `async with`, close the client with `await flashpi.aclose()`.

## Issuing documents

| Document                                    | Method                                      |
| ------------------------------------------- | ------------------------------------------- |
| Invoice (factura)                           | `flashpi.invoices.create(body)`             |
| Credit note (nota de crédito)               | `flashpi.credit_notes.create(body)`         |
| Debit note (nota de débito)                 | `flashpi.debit_notes.create(body)`          |
| Purchase settlement (liquidación de compra) | `flashpi.purchase_settlements.create(body)` |
| Waybill (guía de remisión)                  | `flashpi.waybills.create(body)`             |
| Withholding (comprobante de retención)      | `flashpi.withholdings.create(body)`         |

They all return the document. By default the answer comes right away with the status
`processing`, and the SRI's outcome arrives by webhook. With
`"options": {"waitForAuthorization": True}` the API waits for the SRI (15 s by default, up to
30 s with `waitTimeoutSeconds`) and returns `authorized`, `rejected` or `failed`; if the SRI takes
longer, it returns `processing` or `pending_sri` and the document carries on.

## Documents

```python
from pathlib import Path

document = flashpi.documents.get(invoice["id"])

xml = flashpi.documents.xml(invoice["id"])  # xml["kind"]: "authorized" once the SRI authorized it
pdf = flashpi.documents.pdf(invoice["id"])  # the RIDE, as bytes
Path(f"{invoice['accessKey']}.pdf").write_bytes(pdf)

flashpi.documents.send_email(invoice["id"])  # emails the RIDE and XML to the buyer again
```

## Lists and pagination

A list call returns a page. A `for` loop walks every page, fetching them as you go:

```python
for document in flashpi.documents.list({"status": "authorized", "issueDateFrom": "2026-11-01"}):
    print(document["accessKey"])

page = flashpi.documents.list({"limit": 50})
print(len(page.data))  # the documents of this page
if page.has_next_page():
    page = page.next_page()
```

The filters use the API's names (`issueDateFrom`, `issuerId`). With `AsyncFlashpi`,
`async for` walks every page, and `await flashpi.documents.list()` returns the first page
(`await page.next_page()` the next one).

## Errors

Every API error is an `APIError` subclass chosen by its HTTP status. Branch on `code`, which is
stable and in English; `message` follows the requested language.

```python
from flashpi import APIError, UnprocessableEntityError

try:
    flashpi.invoices.create(body)
except UnprocessableEntityError as error:
    print(error.code)  # "validation_failed", "total_mismatch", ...
    for field in error.errors:
        print(field["field"], field["message"])
    raise
except APIError as error:
    print(error.status, error.code, error.request_id)  # share request_id with support
    raise
```

| Class                      | Status | Example `code`s                                             |
| -------------------------- | ------ | ----------------------------------------------------------- |
| `BadRequestError`          | 400    | `malformed_json`, `invalid_idempotency_key`                 |
| `AuthenticationError`      | 401    | `authentication_required`, `invalid_api_key`                |
| `PermissionDeniedError`    | 403    | `key_read_only`, `key_scope_mismatch`, `ip_not_allowed`     |
| `NotFoundError`            | 404    | `not_found`                                                 |
| `ConflictError`            | 409    | `sequential_already_used`, `ride_not_available`             |
| `UnprocessableEntityError` | 422    | `validation_failed`, `total_mismatch`                       |
| `RateLimitError`           | 429    | `demo_issuer_quota_exceeded`, `account_email_limit_reached` |
| `InternalServerError`      | 5xx    | `internal_error`                                            |
| `APIConnectionError`       | —      | no answer (network); `APITimeoutError` when it timed out    |

All of them derive from `FlashpiError`. Some errors carry extra members in `error.problem`, such
as `documentId`, `limit`, `resetsAt` or `rideStatus`. For Spanish messages:
`Flashpi(language="es")`.

## Retries and idempotency

The SDK retries network errors, timeouts, and 408, 429 (when asked to wait 60 s or less) and
5xx answers up to 2 times, with growing waits. Every POST carries an `Idempotency-Key` that its
retries repeat, so the API never issues twice:

- When a retry finds that the first attempt did create the document, the SDK returns that
  document.
- When the first attempt is still running on the API (for example, the connection dropped while
  it waited for the SRI), the SDK waits for it with the same key, up to the call's time limit,
  without using up retries.

To use your own key (for example your order id), pass it to the call:

```python
flashpi.invoices.create(body, idempotency_key=f"order-{order.id}")
```

If issuing still fails, the error (a `FlashpiError`) carries the key it used in
`error.idempotency_key`. Trying again with `idempotency_key=error.idempotency_key` never issues a
second document: within 24 hours the API returns the first answer again; after that (or if the
API lost track of the first attempt), the call fails with a 422 `idempotency_key_reused` whose
`error.problem["documentId"]` is the existing document (read it with `flashpi.documents.get`).

```python
from flashpi import FlashpiError

try:
    flashpi.invoices.create(body)
except FlashpiError as error:
    if error.idempotency_key:
        save_for_retry(body, error.idempotency_key)  # your retry queue
    raise
```

An `AsyncFlashpi` call whose task is cancelled raises `asyncio.CancelledError`, which is not a
`FlashpiError` and has no key: if you cancel issuing calls, pass your own `idempotency_key`.

Daily limits (such as the demo issuer's quota) are not retried: they are raised as a
`RateLimitError` with `retry_after` in seconds.

## Webhooks

Verify every webhook with the body **exactly as received** (not parsed) and the endpoint's
`whsec_` secret. `unwrap_webhook` needs no API key (it is also `flashpi.webhooks.unwrap`). It
does no I/O, so it is called without `await` in async views too.

With Django:

```python
import os

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from flashpi import WebhookVerificationError, unwrap_webhook


@csrf_exempt
@require_POST
def flashpi_webhook(request: HttpRequest) -> HttpResponse:
    try:
        event = unwrap_webhook(request.body, request.headers, os.environ["FLASHPI_WEBHOOK_SECRET"])
    except WebhookVerificationError:
        return HttpResponse(status=400)

    if event["type"] == "webhook_endpoint.verification":
        # The endpoint's activation: answer the challenge.
        return JsonResponse({"challenge": event["data"]["challenge"]})
    if event["type"] == "invoice.authorized":
        print("Authorized", event["data"]["accessKey"])  # event["data"] is the document
    elif event["type"] == "invoice.rejected":
        print("Rejected", event["data"]["sriMessages"])
    return HttpResponse(status=204)
```

With Flask (its `request.headers` is not a `Mapping`, so pass `dict(request.headers)`):

```python
import os

from flask import Flask, request

from flashpi import WebhookVerificationError, unwrap_webhook

app = Flask(__name__)


@app.post("/webhooks/flashpi")
def flashpi_webhook():
    try:
        event = unwrap_webhook(
            request.get_data(), dict(request.headers), os.environ["FLASHPI_WEBHOOK_SECRET"]
        )
    except WebhookVerificationError:
        return "", 400

    if event["type"] == "webhook_endpoint.verification":
        return {"challenge": event["data"]["challenge"]}
    handle_event(event)  # your code, like the branches of the Django example
    return "", 204
```

With FastAPI:

```python
import os

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from flashpi import WebhookVerificationError, unwrap_webhook

app = FastAPI()


@app.post("/webhooks/flashpi")
async def flashpi_webhook(request: Request) -> Response:
    try:
        event = unwrap_webhook(
            await request.body(), request.headers, os.environ["FLASHPI_WEBHOOK_SECRET"]
        )
    except WebhookVerificationError:
        return Response(status_code=400)

    if event["type"] == "webhook_endpoint.verification":
        return JSONResponse({"challenge": event["data"]["challenge"]})
    handle_event(event)  # your code, like the branches of the Django example
    return Response(status_code=204)
```

Store `event["id"]` and skip repeats: an event can arrive more than once. During a secret
rotation Flashpi signs with both the new and the previous secret, so either works. If the
endpoint uses `thin` mode (no `data`), use `cast(ThinWebhookEvent, unwrap_webhook(...))` and
fetch the event with `flashpi.events.get(event["id"])`.

## Issuers and certificates

These operations need an account-wide key with read and write access.

An issuer starts from its electronic signature (.p12): Flashpi checks it, reads the RUC and asks
the SRI, and returns a `prefill` with what it found so you can build the issuer.

```python
import os
import time
from pathlib import Path

onboarding = flashpi.issuer_onboardings.create(
    {"file": Path("firma.p12").read_bytes(), "password": os.environ["P12_PASSWORD"]}
)
while onboarding["status"] == "verifying":
    time.sleep(2)
    onboarding = flashpi.issuer_onboardings.get(onboarding["id"])
if onboarding["status"] != "ready":
    rejection = onboarding["rejection"]
    raise RuntimeError(rejection["message"] if rejection else onboarding["status"])

prefill = onboarding["prefill"]
if onboarding["existingIssuer"]:
    # You already have that RUC: the certificate is added to that issuer (a renewal).
    completed = flashpi.issuer_onboardings.complete(onboarding["id"])
else:
    # A new RUC: you confirm the issuer's data, starting from the prefill.
    legal_name = prefill and prefill["legalName"]
    address = prefill and prefill["headOfficeAddress"]
    tax_profile = prefill and prefill["taxProfile"]
    rimpe_regime = tax_profile and tax_profile["rimpeRegime"]
    completed = flashpi.issuer_onboardings.complete(
        onboarding["id"],
        {
            "legalName": legal_name or "MY COMPANY S.A.",
            "headOfficeAddress": address or "Av. Amazonas N24-100, Quito",
            "taxProfile": {
                "keepsAccounting": bool(tax_profile and tax_profile["keepsAccounting"]),
                "rimpeRegime": None if rimpe_regime == "general" else rimpe_regime,
                # For a special taxpayer or a withholding agent, add their resolution numbers.
            },
            # When onboarding["rucNeedsConfirmation"] is True, send "ruc" too.
        },
    )

for establishment in flashpi.issuers.establishments.list(completed["issuer"]["id"]):
    print(establishment["code"])
```

The `file` can be the bytes of the .p12 or a file opened in binary mode (`open("firma.p12", "rb")`),
up to 1 MiB.

To **renew an issuer's signature** for test and live mode at once, run the same flow with the
new .p12: Flashpi recognizes the RUC (`existingIssuer`) and `complete()` with no data adds the
certificate. `flashpi.issuers.certificates.upload(issuer_id, {"file": ..., "password": ...})`,
instead, uploads a certificate for the mode of the key you use only (test or live).

## Options

```python
import os

from flashpi import Flashpi

flashpi = Flashpi(
    api_key=os.environ["FLASHPI_API_KEY"],  # defaults to the FLASHPI_API_KEY variable
    language="es",  # language of the messages: "en" (default) or "es"
    timeout=60,  # seconds per attempt (at least the SRI wait + 15 s with waitForAuthorization)
    max_retries=2,  # 0 turns retries off
)
```

Every method also takes the options of that request as keyword arguments: `idempotency_key`,
`timeout`, `max_retries`, `language`, `correlation_id` (your own id, which Flashpi logs) and
`extra_headers`.

```python
document = flashpi.documents.get(document_id, timeout=10, language="es", correlation_id="order-42")
```

To see the HTTP response and the request id, call the method through `with_response`:

```python
result = flashpi.documents.with_response.get(document_id)
print(result.data["status"], result.response.status_code, result.request_id)
```

To send the requests through your own `httpx.Client` (`httpx.AsyncClient` for `AsyncFlashpi`),
for a proxy or a test transport, pass it as `http_client`. You close it; the SDK never follows
redirects.

```python
import httpx

from flashpi import Flashpi

flashpi = Flashpi(http_client=httpx.Client(proxy="http://proxy.internal:3128"))
```

In tests, an `httpx.MockTransport` answers in place of the API.

## Servers only

Your API key is a secret: use the SDK on your servers, never in code that runs on your users'
devices. `repr(flashpi)` shows the environment and the URL, never the key.

## License

[MIT](https://github.com/flashpi1/flashpi-python/blob/main/LICENSE) © 2026 SIGNIADIGITAL S.A.
