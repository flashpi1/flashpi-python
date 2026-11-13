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
- **Same retries and timeouts as Node.** The retry rules above and the timeout of an attempt
  behave as in the Node SDK, with seconds instead of milliseconds. The timeout is one deadline
  for the whole attempt, from sending it to reading the whole answer, as Node's
  AbortController: `AsyncFlashpi` wraps the attempt in `asyncio.timeout()` (cancelling the task
  still cancels the call), and `Flashpi` limits each network operation of the attempt to the
  time it has left, so an answer that trickles in times out too (with a caller's `http_client`,
  see Requests below).
- **Porting choices the owner confirmed on 2026-11-13.** Chosen while porting, then confirmed
  as proposed:
  - `list()` takes its filters as a dict with the API's camelCase keys,
    `documents.list({"status": "authorized", "issueDateFrom": "2026-11-01"}, timeout=30)`, as
    Node's `list(params, options)` and the create bodies.
  - Node's per-call `.withResponse()` is a view on each resource,
    `client.documents.with_response.get(id)`, returning `APIResponse(data, response,
    request_id)`.
  - Models are imported from `flashpi.types` (`from flashpi.types import Document`); the package
    root exports only the clients, errors, pages, options and webhook helpers.
  - `unwrap_webhook` and `verify_webhook_signature` are synchronous on both clients (Node's are
    async only because of Web Crypto); the webhook `now` is a `datetime` or Unix seconds.
  - Redirects are never followed. `AsyncFlashpi` runs on asyncio only, not trio. The User-Agent
    is `flashpi-python/<version>`.
  - Misusing an argument in a way a type checker would refuse raises `TypeError` or
    `ValueError` (unknown option names, a body that is not JSON, bad webhook `tolerance` or
    `now`, header names or values that are not text, a .p12 that is not bytes or a binary file);
    bad timeouts, `max_retries`, ids, `base_url` and API key stay `FlashpiError`, as in Node.

### Chosen while porting (to confirm)

- **Shape of the API.** Resource classes are in `flashpi.resources` (`Async` prefix for the
  async ones; `StatusResource` so it does not clash with the `Status` model). On `AsyncFlashpi`,
  `list()` returns an `AsyncPaginator` without an `await`: `async for` walks every item, `await`
  gives the first page. `issuer_onboardings.complete(id)` sends `{}` and
  `webhook_endpoints.rotate_secret(id)` no body when no body is given;
  `documents.send_email(id)` always sends `{}`.
- **Errors.** .p12 contents (empty, over 1 MiB, password not text) raise `FlashpiError`, as in
  Node. A request httpx refuses to write (h11's `LocalProtocolError`) raises a `FlashpiError`
  at once, not a retried `APIConnectionError`, and without httpx's reason, which quotes the
  refused header (possibly the Authorization one).
- **Headers.** Every value that becomes a header (`idempotency_key`, `correlation_id`,
  `language`, `extra_headers`, and the client's `default_headers` and `language`) is checked by
  the SDK before anything is sent, so a bad one is never retried as a network failure. As Node's
  `Headers`, the spaces, tabs and line breaks around a value are trimmed, and the trimmed
  Idempotency-Key is the one on errors. A line break, NUL or another control character other
  than a tab left inside a value, or a name that is not an RFC 9110 token, raises `ValueError`
  (Node: a `TypeError` from `Headers`; for control characters other than CR, LF and NUL, Node
  fails only when sending, as a retried network error); a value that is not text raises
  `TypeError` (Node turns it into text). Text outside ASCII is sent as UTF-8, as httpx does, on
  every request and in `default_headers`; a lone surrogate (a framework's escape of bytes that
  are not UTF-8), which has no UTF-8, raises `ValueError`. `Content-Length` and
  `Transfer-Encoding` raise `ValueError` too, since httpx sets them from the body (Node's fetch
  refuses `Transfer-Encoding` before sending and fails a wrong `Content-Length` while sending).
  An empty `language`, or one of spaces only, is not sent, as in Node: a call keeps the client's
  language, and a client sends none.
  The messages never show the value.
- **API key.** It is trimmed as Node's `trim()` does, a byte order mark (U+FEFF) included.
  Besides the prefix, the key must be visible ASCII without spaces: a key with a space, a line
  break, a control character or a character outside ASCII raises `FlashpiError` when the client
  is created, without showing the key (Node sends inner spaces and leaks a key with a line break
  in its `TypeError`).
- **Requests.** On `Flashpi`, the httpx client the SDK creates gets a network backend that
  limits connecting, the TLS handshake, each write and each read of an attempt to the time the
  attempt has left, also through the proxies of the environment, which it keeps. It reaches
  httpcore, which httpx always installs, through private attributes of httpx and httpcore that
  the tests pin. Only a DNS lookup, which Python cannot interrupt, and connecting to a host that
  has several addresses can run past the deadline. With a caller's `http_client`, the deadline
  is checked as each chunk of the answer's body arrives and once the answer is read: before the
  body, httpx limits connecting, each write, waiting for a pooled connection and each read of
  the status line and headers to the timeout one by one, so headers that trickle in can keep an
  attempt going far past its timeout, and a body that the client's own response hooks read is
  checked only once it has been read. The in-progress wait counts wall time. Timeouts are capped
  at 2147483.647 s, Node's `setTimeout` limit, only so both SDKs accept the same values. A 3xx
  answer raises `APIError`, `base_url` must be an http(s) URL with a host, and the client closes
  only an httpx client it created. In an issue with `options.waitForAuthorization`, a
  `waitTimeoutSeconds` that is not a number counts as the default 15. A .p12 upload sends the
  password field before the file, whose content type is always `application/x-pkcs12`. A file
  object is read once, in pieces, up to one byte past 1 MiB (a bigger file is refused without
  being read whole, as "more than 1048576 bytes"), and not closed; an async reader
  (`async def read`) is refused with `TypeError`, and a non-blocking stream with no data ready
  (its `read()` returns None) with `FlashpiError`. The repr of a multipart body lists only its
  part names, never the .p12 or its password.
- **Secrets in tracebacks.** Error trackers record the local variables of every frame an error
  passes through, and scrub them by name (`api_key`, `secret`, `password`) at best. So no frame
  of the SDK that an error passes through keeps the SDK's secrets under another name: a webhook
  verification error leaves neither the decoded signing key nor the expected signature behind,
  a failed .p12 upload leaves neither the file nor its password, whatever raised (the
  traceback is kept, down to a file's own `read()`), and the API key stays only in the caller's
  `api_key` argument: no other local of a failed request (whose `httpx.Headers` hide it only in
  their repr) or of a refused setting or key keeps it. The frames of httpx and httpcore, in the
  cause of a network error, are not changed, and neither are the headers a caller passes, which
  the caller's own frames hold too.
- **Runtimes.** There is no counterpart of Node's browser guard (Pyodide is not refused).
- **Webhooks.** A signed body that is not a JSON object is refused. A `webhook-id` that cannot
  be encoded as UTF-8 (a framework's surrogate escape of other bytes) ends at
  `no_matching_signature`, as in Node, once a body that is not text or bytes has been refused
  as `invalid_payload`. Thin endpoints use
  `cast(ThinWebhookEvent, unwrap_webhook(...))`. Headers are any `Mapping`: Flask's
  `request.headers` (Werkzeug's `Headers`) is not one, although it works at run time, so the
  README passes `dict(request.headers)`.
- **Types.** A generator of our own, standard library only (`scripts/openapi.py`), instead of
  datamodel-code-generator: no large dev dependency, a deterministic output that already passes
  Ruff and pyright, and a failure on any construct it does not know. Inline enums are named after
  their schema and property (`DocumentStatus`, `CreateWebhookEndpointEnabledEventsItem`).
  `CertificateUpload.file` also takes a binary file object. The daily sync downloads the
  contract over HTTPS only and refuses a redirect to any other scheme (Node's script has no such
  check).
- **README examples.** Every python block of both READMEs becomes a module in
  `tests/examples/readme/` (`scripts/readme.py`) that pyright and Ruff check and the tests keep in
  step with the READMEs, the counterpart of Node's type-checked `test/examples/readme.ts`. The
  Django, Flask and FastAPI examples are checked against small stubs with those frameworks' real
  signatures, so none of them becomes a dependency. The READMEs link to each other and to the
  license with absolute URLs, since PyPI shows `README.md` and cannot follow relative links; the
  package check fails on one.
- **Live suite.** Run with `uv run pytest -m live --no-cov`. Besides Node's steps it reads the
  status and walks the events with `AsyncFlashpi`; it still issues exactly one invoice.
- **CI.** Lint, format, pyright and tests with a 95 % coverage gate on the Python of
  `.python-version`; the tests on 3.11 to 3.15; the tests on 3.11 with the lowest direct
  dependencies (httpx 0.27); and a build whose wheel and sdist are checked file by file
  (`scripts/package_check.py`) and whose wheel is installed alone and used on 3.11 and 3.15. The
  sdist carries the tests and what they need, so they run from it. setup-uv installs the latest
  uv, except in the release's build job, which pins it by version and by the SHA-256 of its
  archive; the lockfile is checked with `--locked`.
- **Releases.** release-please's `python` type updates `pyproject.toml`; `_version.py` and the
  package's entry in `uv.lock` are extra files, since `uv sync --locked` fails when the lockfile
  and `pyproject.toml` disagree. A build job, with a read-only token and no secret, builds the
  tag with `uv build --no-sources --build-constraints build-constraints.txt --require-hashes`
  and no cache and checks the files. The publish job, the only
  one with the `id-token` permission, checks out nothing and runs no code of the repository or
  of its dependencies (not even the build backend): it downloads those files and uploads them
  with trusted publishing and PEP 740 attestations. Neither runs the tests (CI ran them on the
  release PR). The build backend is pinned for every build of the workflows: `build.in` names
  hatchling 1.33.0, and `build-constraints.txt`, generated from it with
  `uv pip compile --generate-hashes`, fixes it and its dependencies by version and hash, so the
  build refuses anything else (Dependabot does not update it). `pyproject.toml` keeps
  `hatchling>=1.33`, so others can still build the sdist. PyPI accepts a pending
  publisher before the project exists, so unlike npm, 0.1.0 is published by the workflow too.
  PyPI shows `README.md`, the Spanish one, as npm does.
