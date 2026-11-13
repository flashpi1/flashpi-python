# Decisions

Decisions about flashpi, the Python SDK, newest first. Its design follows the Node.js SDK,
[@flashpi/node](https://github.com/flashpi1/flashpi-node), whose
[decisions](https://github.com/flashpi1/flashpi-node/blob/main/docs/decisions.md) apply here
unless an entry says otherwise. Entries marked as the owner's were taken with the Flashpi
product owner; the others were chosen while porting, after the Node SDK where the owner had not
decided, and are listed so they can be confirmed or changed before 1.0.

## 2026-11-13: the Python SDK

### The owner's decisions

- **Package and repository.** `flashpi` on PyPI (`from flashpi import Flashpi, AsyncFlashpi`),
  public repository `flashpi1/flashpi-python`, MIT license held by SIGNIADIGITAL S.A. Python 3.11
  or later, tested on 3.11 to 3.15. First version 0.1.0 through release-please (the manifest
  starts at 0.0.0 with `initial-version` 0.1.0, as the Node SDK ended up).
- **Two clients with the same API.** `Flashpi` (sync) and `AsyncFlashpi` (asyncio). The only
  runtime dependency is httpx (`>=0.27,<1`). Models are `TypedDict`s generated from the OpenAPI
  document: dictionary access with the API's camelCase keys, no pydantic. The package ships
  `py.typed`.
- **The Node SDK's design.** Resource style (`client.invoices.create(body)`,
  `client.documents.list(...)`, `client.issuers.establishments.create(issuer_id, body)`). Every
  POST carries an Idempotency-Key (uuid4 unless the caller gives one), serialized once and reused
  by its retries. Up to 2 retries with backoff from 0.5 s to 8 s and up to 25 % jitter after
  network errors, timeouts, 408, 429 and 5xx (not 501 or `demo_issuer_unavailable`), honoring a
  Retry-After of 60 s or less. A 409 `idempotency_key_in_progress` is waited for (1 s up to 5 s,
  within the call's time budget) only when an earlier attempt may have reached the API. A retried
  document POST answered 422 `idempotency_key_reused` with `problem.documentId` returns that
  document, and a retried DELETE answered 404 counts as done. English messages by default,
  `language="es"` per client or per call. The key falls back to `FLASHPI_API_KEY`. Automatic
  pagination. Standard Webhooks verification (unwrap and verify, `whsec_` secrets of 24 to 64
  bytes, tolerance, several signatures during a rotation, constant-time comparison, a typed
  `WebhookVerificationError.reason`). The live API test runs on release PRs only. READMEs in
  Spanish (`README.md`) and English (`README.en.md`).
- **Python idioms.** snake_case methods and resources (`credit_notes`, `purchase_settlements`,
  `issuer_onboardings`, `webhook_endpoints`, `send_email`, ...). Per-call options are keyword
  arguments (`idempotency_key`, `timeout`, `max_retries`, `language`, `correlation_id`,
  `extra_headers`). Timeouts are in seconds (a float), not milliseconds. Errors never shadow
  builtins: `APIConnectionError` and `APITimeoutError` (both `FlashpiError`s) stand for Node's
  `ConnectionError` and `TimeoutError`. Cancelling an async call is cancelling its task, and
  `asyncio.CancelledError` is never swallowed. Clients are context managers with `close()` and
  `aclose()`. The API key never appears in `repr()`, `str()` or logs. httpx never follows
  redirects.
- **Tooling.** uv with the hatchling build backend, Ruff (lint and format), pyright strict and
  pytest; async tests with anyio's pytest plugin on asyncio, and HTTP mocked with
  `httpx.MockTransport`.

### Chosen while porting (to confirm)

- **Shape of the API.** Models live in `flashpi.types` (`from flashpi.types import Document`);
  the package root exports the clients, errors, pages, options and webhook helpers. Resource
  classes are in `flashpi.resources` (`Async` prefix for the async ones; `StatusResource` so it
  does not clash with the `Status` model). `list()` takes its filters as a dict with the API's
  camelCase keys, `documents.list({"status": "authorized"}, timeout=30)`, as Node's
  `list(params, options)`. On `AsyncFlashpi`, `list()` returns an `AsyncPaginator` without an
  `await`: `async for` walks every item, `await` gives the first page. Node's per-call
  `.withResponse()` is a view on each resource, `client.documents.with_response.get(id)`,
  returning `APIResponse(data, response, request_id)`. `issuer_onboardings.complete(id)` sends
  `{}` and `webhook_endpoints.rotate_secret(id)` no body when no body is given;
  `documents.send_email(id)` always sends `{}`.
- **Errors.** Values a type checker would refuse (unknown option names, a body that is not
  JSON, bad webhook `tolerance` or `now`, header values that are not text, a .p12 that is not
  bytes or a binary file) raise `TypeError` or `ValueError`; bad timeouts, retries, ids, base URL,
  API key and .p12 contents (empty, over 1 MiB, password not text) raise `FlashpiError`, as in
  Node. Header values are checked by the SDK itself, because httpx 0.27 and 0.28 fail on them
  differently.
- **Requests.** User-Agent `flashpi-python/<version>`. The timeout of an attempt is httpx's
  (connect, each read, write and pool separately), not one deadline per attempt as Node's
  AbortController; the in-progress wait still counts wall time. Timeouts are capped at
  2147483.647 s, Node's `setTimeout` limit, only so both SDKs accept the same values. A 3xx
  answer raises `APIError`, `base_url` must be an http(s) URL with a host, and the client closes
  only an httpx client it created. In a sync-mode issue, a `waitTimeoutSeconds` that is not a
  number counts as the default 15. A .p12 upload sends the password field before the file, whose
  content type is always `application/x-pkcs12`; a file object is read once and not closed.
- **Runtimes.** `AsyncFlashpi` sleeps with `asyncio.sleep`, so it runs on asyncio, not trio.
  There is no counterpart of Node's browser guard (Pyodide is not refused).
- **Webhooks.** `unwrap_webhook` and `verify_webhook_signature` are synchronous on both clients
  (Node's are async only because of Web Crypto); `now` is a `datetime` or Unix seconds. A signed
  body that is not a JSON object is refused. Thin endpoints use
  `cast(ThinWebhookEvent, unwrap_webhook(...))`. Headers are any `Mapping`: Flask's
  `request.headers` (Werkzeug's `Headers`) is not one, although it works at run time, so the
  README passes `dict(request.headers)`.
- **Types.** A generator of our own, standard library only (`scripts/openapi.py`), instead of
  datamodel-code-generator: no large dev dependency, a deterministic output that already passes
  Ruff and pyright, and a failure on any construct it does not know. Inline enums are named after
  their schema and property (`DocumentStatus`, `CreateWebhookEndpointEnabledEventsItem`).
  `CertificateUpload.file` also takes a binary file object.
- **README examples.** Every python block of both READMEs becomes a module in
  `tests/examples/readme/` (`scripts/readme.py`) that pyright and Ruff check and the tests keep in
  step with the READMEs, the counterpart of Node's type-checked `test/examples/readme.ts`. The
  Django, Flask and FastAPI examples are checked against small stubs with those frameworks' real
  signatures, so none of them becomes a dependency.
- **Live suite.** Run with `uv run pytest -m live --no-cov`. Besides Node's steps it reads the
  status and walks the events with `AsyncFlashpi`; it still issues exactly one invoice.
- **CI.** Lint, format, pyright and tests with a 95 % coverage gate on the Python of
  `.python-version`; the tests on 3.11 to 3.15; the tests on 3.11 with the lowest direct
  dependencies (httpx 0.27); and a build whose wheel and sdist are checked file by file
  (`scripts/package_check.py`) and whose wheel is installed alone and used on 3.11 and 3.15. The
  sdist carries the tests and what they need, so they run from it. setup-uv installs the latest
  uv; the lockfile is checked with `--locked`.
- **Releases.** release-please's `python` type updates `pyproject.toml`; `_version.py` and the
  package's entry in `uv.lock` are extra files, since `uv sync --locked` fails when the lockfile
  and `pyproject.toml` disagree. The publish job builds the tag with `uv build --no-sources` and
  no cache, checks the files, and uploads them with trusted publishing and PEP 740 attestations.
  It runs no tests (CI ran them on the release PR), to keep dependency code away from its
  `id-token` permission. PyPI accepts a pending publisher before the project exists, so unlike
  npm, 0.1.0 is published by the workflow too. PyPI shows `README.md`, the Spanish one, as npm
  does.
