"""Requests to the Flashpi API: retries, timeouts, idempotency and typed errors.

The rules live once, in `plan()`: a generator that yields what to do next (send an attempt, sleep,
read a document) and receives the outcome. `SyncEngine` runs it on an `httpx.Client` and
`AsyncEngine` on an `httpx.AsyncClient`, so `Flashpi` and `AsyncFlashpi` behave the same.
"""

import asyncio
import json
import random
import time
import uuid
from collections.abc import Generator, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeAlias, TypedDict, TypeVar, cast
from urllib.parse import quote, urlencode

import httpx

from ._errors import APIConnectionError, APIError, APITimeoutError, FlashpiError, api_error
from ._response import APIResponse
from ._validate import MAX_TIMEOUT, checked_headers, header_value, valid_retries, valid_timeout
from ._version import VERSION
from .types import Language

T = TypeVar("T")

Method: TypeAlias = Literal["GET", "POST", "PATCH", "DELETE"]
ResponseType: TypeAlias = Literal["json", "text", "bytes", "none"]
"""How to read a successful answer: parsed JSON, text, raw bytes, or nothing (None)."""

USER_AGENT = f"flashpi-python/{VERSION}"

MAX_RETRY_AFTER = 60.0
"""Longest `Retry-After`, in seconds, the SDK waits for by itself; longer waits (daily quotas)
are raised."""

INITIAL_RETRY_DELAY = 0.5
MAX_RETRY_DELAY = 8.0
# Waits between checks on an earlier attempt that the API is still running.
IN_PROGRESS_FIRST_WAIT = 1.0
IN_PROGRESS_MAX_WAIT = 5.0
IN_PROGRESS = "idempotency_key_in_progress"

# Looked up on every call, so tests can replace them.
_monotonic = time.monotonic
_random = random.random
_sleep = time.sleep
_async_sleep = asyncio.sleep


class RequestOptions(TypedDict, total=False):
    """Options every method accepts as keyword arguments. None means the client's setting."""

    idempotency_key: str | None
    """Idempotency-Key of a POST: 1 to 255 visible ASCII characters (no spaces), unique per
    operation, such as your order id or a UUID. The SDK creates one when it is missing and reuses
    it on its retries, so a retry never issues a document twice. Ignored by other methods. An
    `Idempotency-Key` in `extra_headers` works too."""

    timeout: float | None
    """Seconds each attempt may take, from sending it to reading the whole answer, overriding the
    client's `timeout`."""

    max_retries: int | None
    """Retries after network errors, timeouts, 429 and 5xx, overriding the client's
    `max_retries`."""

    language: Language | None
    """Language of the API's messages for this request, overriding the client's `language`."""

    correlation_id: str | None
    """Your own id for the request (`X-Correlation-Id`, 1 to 128 of `A-Za-z0-9._:/+=-`), echoed
    back and logged by Flashpi."""

    extra_headers: Mapping[str, str] | None
    """Extra headers for this request. They never replace the API key."""


_OPTION_NAMES = frozenset(RequestOptions.__annotations__)


@dataclass(frozen=True)
class Multipart:
    """A multipart/form-data body. It holds bytes, so every attempt sends the same body."""

    fields: Mapping[str, str]
    """Text fields."""

    files: Mapping[str, tuple[str, bytes, str]]
    """Files: part name to (file name, content, content type)."""

    def __repr__(self) -> str:
        # Only the part names: the values are a .p12 and its password, and a repr ends up in
        # tracebacks and in error trackers that record local variables (`spec`, `step`).
        return f"Multipart(fields={list(self.fields)!r}, files={list(self.files)!r})"


@dataclass(frozen=True, kw_only=True)
class RequestSpec(Generic[T]):
    """One API operation, as the resources declare it. `T` is the type of its data."""

    method: Method
    path: str
    """The path, built with `path_of()` when it carries ids."""

    query: Mapping[str, object] | None = None
    """Query parameters; None values are left out, booleans are sent as true and false."""

    body: object = None
    """A JSON body, serialized once for every attempt. None sends no body."""

    multipart: Multipart | None = None
    """A multipart body, instead of `body`."""

    accept: str = "application/json"
    """The Accept header."""

    response_type: ResponseType = "json"
    """How to read a successful answer."""

    options: RequestOptions | None = None
    """The caller's options."""

    min_timeout: float = 0
    """A floor, in seconds, for the per-attempt timeout of requests the API holds open (issuing
    with `options.waitForAuthorization`)."""

    recover_document: bool = False
    """For document POSTs: when a retry of this call is answered 422 `idempotency_key_reused` with
    a `documentId`, an earlier attempt created the document, so the call returns
    GET /v1/documents/{documentId} instead of failing."""


@dataclass(frozen=True)
class ClientConfig:
    """The settings of a client that the requests need."""

    api_key: str = field(repr=False)
    base_url: str
    timeout: float
    max_retries: int
    language: Language | None
    default_headers: Mapping[str, str]


# The steps of a request plan.


@dataclass(frozen=True)
class Attempt:
    """Send one attempt; the outcome is an APIResponse or an APIError (or a raised FlashpiError)."""

    method: Method
    url: str
    headers: httpx.Headers
    content: bytes | None
    multipart: Multipart | None
    timeout: float
    response_type: ResponseType


@dataclass(frozen=True)
class Sleep:
    """Wait before the next attempt."""

    seconds: float


@dataclass(frozen=True)
class Fetch:
    """Run another request (reading a recovered document); the outcome is its APIResponse."""

    spec: RequestSpec[Any]


Step: TypeAlias = Attempt | Sleep | Fetch
Plan: TypeAlias = Generator[Step, object, APIResponse[Any]]


@dataclass(frozen=True)
class Call:
    """What every attempt of one call shares, resolved before the first one is sent."""

    options: RequestOptions
    max_retries: int
    timeout: float
    url: str
    idempotency_key: str | None
    content: bytes | None


def prepare(config: ClientConfig, spec: RequestSpec[Any]) -> Call:
    """Checks the options and builds what the attempts share. Raises before anything is sent."""
    options = check_options(spec.options)
    max_retries = config.max_retries
    if options.get("max_retries") is not None:
        max_retries = valid_retries("max_retries", options.get("max_retries"))
    timeout = config.timeout
    if options.get("timeout") is not None:
        timeout = valid_timeout("timeout", options.get("timeout"))
    return Call(
        options=options,
        max_retries=max_retries,
        timeout=min(max(timeout, spec.min_timeout), MAX_TIMEOUT),
        url=build_url(config.base_url, spec.path, spec.query),
        idempotency_key=idempotency_key_of(spec.method, options),
        # Serialized once: every attempt sends the same bytes under the same Idempotency-Key,
        # even when the caller changes the object meanwhile.
        content=None if spec.body is None or spec.multipart is not None else encode_json(spec.body),
    )


def plan(config: ClientConfig, spec: RequestSpec[Any]) -> Plan:
    """The steps of one call, with its retries and recoveries. It returns the call's result."""
    call = prepare(config, spec)
    started = _monotonic()
    attempt = retries = waits = 0
    # Whether an earlier attempt may have reached the API without its answer reaching us (a
    # network error, a timeout, or a 5xx from a proxy). Only then can a 409
    # idempotency_key_in_progress be this call's own attempt still running.
    unanswered = False

    while True:
        headers = build_headers(config, spec, call.options, call.idempotency_key)
        failure: APIError | APIConnectionError
        try:
            outcome = yield Attempt(
                spec.method,
                call.url,
                headers,
                call.content,
                spec.multipart,
                call.timeout,
                spec.response_type,
            )
        except APIConnectionError as error:
            failure = error
        except FlashpiError as error:
            error.idempotency_key = call.idempotency_key
            raise
        else:
            if not isinstance(outcome, APIError):
                return cast("APIResponse[Any]", outcome)
            failure = outcome
        failure.idempotency_key = call.idempotency_key

        if attempt > 0 and isinstance(failure, APIError):
            document_id = recoverable_document(spec, failure)
            if document_id is not None:
                return (yield from recover_document(call, document_id))
            # A DELETE retried after a lost answer finds the resource already gone.
            if spec.method == "DELETE" and failure.status == 404:
                return deleted(spec.method, call.url, failure)
            # This call's earlier attempt is still running on the API (a sync issue whose answer
            # was lost): wait for it with the same key while the call has time left. These checks
            # do not count as retries; once the time is up, the normal retry rules apply.
            if unanswered and failure.status == 409 and failure.code == IN_PROGRESS:
                wait = min(IN_PROGRESS_FIRST_WAIT * 2 ** min(waits, 16), IN_PROGRESS_MAX_WAIT)
                if _monotonic() + wait - started <= call.timeout:
                    waits += 1
                    attempt += 1
                    yield Sleep(wait)
                    continue

        if isinstance(failure, APIConnectionError) or (
            failure.status >= 500 and failure.problem is None
        ):
            unanswered = True
        delay = retry_delay(failure, retries)
        if delay is None or retries >= call.max_retries:
            raise failure
        retries += 1
        attempt += 1
        yield Sleep(delay)


def recover_document(call: Call, document_id: str) -> Plan:
    """Reads the document an earlier attempt of the call created.

    A failure to read it keeps the call's key on the error, so trying again later with that key
    returns the document instead of issuing another.
    """
    try:
        read = RequestSpec[Any](
            method="GET",
            path=path_of("/v1/documents/{}", document_id),
            options=without_idempotency_key(call.options),
        )
        recovered = yield Fetch(read)
    except FlashpiError as error:
        error.idempotency_key = call.idempotency_key
        raise
    return cast("APIResponse[Any]", recovered)


def retry_delay(failure: FlashpiError, retries: int) -> float | None:
    """Seconds to wait before retrying, or None when the failure must not be retried.

    Retried: network errors and timeouts, 408, 429 and 5xx except 501 (with a `Retry-After` of
    `MAX_RETRY_AFTER` or less), and 409 `idempotency_key_in_progress` (an attempt with the same key
    is still running). POSTs are safe to retry because they keep their Idempotency-Key.
    """
    if isinstance(failure, APIConnectionError):
        return backoff(retries)
    if not isinstance(failure, APIError):
        return None
    if failure.status == 409:
        return (
            max(IN_PROGRESS_FIRST_WAIT, backoff(retries)) if failure.code == IN_PROGRESS else None
        )
    status = failure.status
    transient = status in (408, 429) or (status >= 500 and status != 501)
    # The shared demo certificate is missing: no retry within seconds will fix that.
    if not transient or failure.code == "demo_issuer_unavailable":
        return None
    retry_after = failure.retry_after
    if retry_after is None:
        return backoff(retries)
    return float(retry_after) if retry_after <= MAX_RETRY_AFTER else None


def backoff(retries: int) -> float:
    """Exponential backoff from 0.5 s up to 8 s, minus up to 25 % of jitter."""
    delay = min(INITIAL_RETRY_DELAY * 2 ** min(retries, 16), MAX_RETRY_DELAY)
    return round(delay * (1 - _random() * 0.25), 3)


def recoverable_document(spec: RequestSpec[Any], failure: APIError) -> str | None:
    """The id of the document an earlier attempt of this call created, if the answer shows one."""
    if (
        not spec.recover_document
        or failure.status != 422
        or failure.code != "idempotency_key_reused"
    ):
        return None
    document_id = cast("dict[str, object]", failure.problem or {}).get("documentId")
    return document_id if isinstance(document_id, str) and document_id != "" else None


def deleted(method: Method, url: str, failure: APIError) -> APIResponse[Any]:
    """The result of a DELETE whose resource is gone: a 204 with the 404's headers."""
    dropped = {"content-length", "content-type", "content-encoding", "transfer-encoding"}
    headers = [
        (name, value)
        for name, value in failure.headers.multi_items()
        if name.lower() not in dropped
    ]
    response = httpx.Response(204, headers=headers, request=httpx.Request(method, url))
    return APIResponse(data=None, response=response, request_id=failure.request_id)


def check_options(options: RequestOptions | None) -> RequestOptions:
    """The caller's options with the values that become headers checked and trimmed
    (`header_value`), so the attempts, the errors and a recovered read all use the same ones."""
    if not options:
        return {}
    unknown = sorted(set(options) - _OPTION_NAMES)
    if unknown:
        raise TypeError(f"Unknown request options: {', '.join(unknown)}")
    checked: RequestOptions = {**options}
    extra_headers = options.get("extra_headers")
    if extra_headers is not None:
        checked["extra_headers"] = checked_headers("extra_headers", extra_headers)
    idempotency_key = options.get("idempotency_key")
    if idempotency_key is not None:
        checked["idempotency_key"] = header_value("idempotency_key", idempotency_key)
    correlation_id = options.get("correlation_id")
    if correlation_id is not None:
        checked["correlation_id"] = header_value("correlation_id", correlation_id)
    language = options.get("language")
    if language is not None:
        checked["language"] = cast("Language", header_value("language", language))
    return checked


def without_idempotency_key(options: RequestOptions) -> RequestOptions:
    read: RequestOptions = {**options}
    read.pop("idempotency_key", None)
    return read


def idempotency_key_of(method: Method, options: RequestOptions) -> str | None:
    """The caller's Idempotency-Key of a POST (option or header), or a new one."""
    if method != "POST":
        return None
    key = options.get("idempotency_key")
    if key is not None:
        return key
    # The last spelling wins, as in `build_headers`. Not through httpx.Headers(mapping), which
    # encodes the values as ASCII and joins repeated names.
    header = None
    for name, value in (options.get("extra_headers") or {}).items():
        if name.lower() == "idempotency-key":
            header = value
    return header if header is not None else str(uuid.uuid4())


def encode_json(body: object) -> bytes:
    """Compact UTF-8 JSON, like JSON.stringify. NaN and infinities are refused (ValueError)."""
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def build_url(base_url: str, path: str, query: Mapping[str, object] | None) -> str:
    """The URL of a request. Query values that are None are left out."""
    pairs = [
        (name, query_value(value)) for name, value in (query or {}).items() if value is not None
    ]
    search = urlencode(pairs)
    return f"{base_url.rstrip('/')}{path}{f'?{search}' if search else ''}"


def query_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_headers(
    config: ClientConfig,
    spec: RequestSpec[Any],
    options: RequestOptions,
    idempotency_key: str | None,
) -> httpx.Headers:
    """The headers of an attempt, from the lowest priority to the highest."""
    headers = httpx.Headers({"accept": spec.accept, "user-agent": USER_AGENT})
    # Client language, client headers, request language, request headers, then the SDK's own.
    if config.language:
        headers["accept-language"] = config.language
    for name, value in config.default_headers.items():
        headers[name] = value
    language = options.get("language")
    if language:
        headers["accept-language"] = language
    for name, value in (options.get("extra_headers") or {}).items():
        headers[name] = value
    correlation_id = options.get("correlation_id")
    if correlation_id is not None:
        headers["x-correlation-id"] = correlation_id
    if idempotency_key is not None:
        headers["idempotency-key"] = idempotency_key
    if spec.multipart is not None:
        # httpx sets the multipart content type with its boundary.
        headers.pop("content-type", None)
    elif spec.body is not None:
        headers["content-type"] = "application/json"
    headers["authorization"] = f"Bearer {config.api_key}"
    return headers


def path_of(template: str, *ids: str) -> str:
    """A path from a template with `{}` placeholders, each id percent-encoded.

    `path_of("/v1/issuers/{}", issuer_id)`. Rejects empty ids, and `.` and `..`, which URL
    normalization would turn into the parent path (another resource).
    """
    parts = template.split("{}")
    if len(parts) != len(ids) + 1:
        raise ValueError(f"{template} has {len(parts) - 1} placeholders, not {len(ids)}")
    shown = template.replace("{}", "{id}")
    path = parts[0]
    for value, part in zip(ids, parts[1:], strict=True):
        if not isinstance(cast("object", value), str) or value.strip() == "":
            raise FlashpiError(f"Missing id in {shown}: got {value!r}")
        if value in (".", ".."):
            raise FlashpiError(f"Invalid id in {shown}: {value!r}")
        # The characters encodeURIComponent leaves as they are.
        path += quote(value, safe="!~*'()") + part
    return path


# Reading the answer of an attempt.


def read_response(
    response: httpx.Response, response_type: ResponseType
) -> APIResponse[Any] | APIError:
    """The data of a successful answer, or the APIError of an error status."""
    if not response.is_success:
        return api_error(response.status_code, response.headers, decode(response.content))
    data = read_data(response, response_type)
    return APIResponse(
        data=data, response=response, request_id=response.headers.get("x-request-id")
    )


def read_data(response: httpx.Response, response_type: ResponseType) -> object:
    if response_type == "bytes":
        return response.content
    text = decode(response.content)
    if response_type == "text":
        return text
    if response_type == "none" or response.status_code == 204 or not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, RecursionError) as error:
        raise FlashpiError(
            f"The API answered {response.status_code} with a body that is not JSON"
        ) from error


def decode(content: bytes) -> str:
    """UTF-8 text, with invalid bytes replaced (like the Node SDK's TextDecoder)."""
    return content.decode("utf-8", errors="replace")


def timeout_error(step: Attempt) -> APITimeoutError:
    seconds = f"{step.timeout:.3f}".rstrip("0").rstrip(".")
    return APITimeoutError(f"{step.method} {step.url} timed out after {seconds} seconds")


def invalid_request_error(step: Attempt) -> FlashpiError:
    """httpx refused to send the request (h11's LocalProtocolError). Not retried, and without
    httpx's reason, which quotes the header it refused: that may be the Authorization header."""
    return FlashpiError(f"{step.method} {step.url} was not sent: httpx refused it as invalid HTTP")


def connection_error(step: Attempt, error: Exception) -> APIConnectionError:
    reason = str(error) or type(error).__name__
    return APIConnectionError(f"{step.method} {step.url} failed: {reason}")


def request_arguments(step: Attempt) -> dict[str, Any]:
    """The arguments of `httpx.Client.build_request` for an attempt."""
    arguments: dict[str, Any] = {
        "method": step.method,
        "url": step.url,
        "headers": step.headers,
        "content": step.content,
        "timeout": httpx.Timeout(step.timeout),
    }
    if step.multipart is not None:
        arguments["data"] = dict(step.multipart.fields)
        arguments["files"] = dict(step.multipart.files)
    return arguments


class SyncEngine:
    """Runs the request plans of a `Flashpi` client on an `httpx.Client`."""

    def __init__(self, config: ClientConfig, http_client: httpx.Client) -> None:
        self.config = config
        self.http_client = http_client

    def request(self, spec: RequestSpec[T]) -> APIResponse[T]:
        steps = plan(self.config, spec)
        try:
            step = next(steps)
            while True:
                outcome: object = None
                thrown: FlashpiError | None = None
                try:
                    if isinstance(step, Sleep):
                        _sleep(step.seconds)
                    elif isinstance(step, Fetch):
                        outcome = self.request(step.spec)
                    else:
                        outcome = self._send(step)
                except FlashpiError as error:
                    thrown = error
                step = steps.send(outcome) if thrown is None else steps.throw(thrown)
        except StopIteration as stop:
            return cast("APIResponse[T]", stop.value)
        finally:
            steps.close()

    def _send(self, step: Attempt) -> APIResponse[Any] | APIError:
        """One attempt within its deadline. httpx limits connecting, sending and each read to the
        attempt's timeout; the deadline is checked as each chunk of the answer arrives, so an
        answer that trickles in still times out (one stalled read can add up to one timeout)."""
        request = self.http_client.build_request(**request_arguments(step))
        deadline = _monotonic() + step.timeout
        try:
            response = self.http_client.send(request, follow_redirects=False, stream=True)
            try:
                stream = cast("httpx.SyncByteStream", response.stream)
                response.stream = _DeadlineStream(stream, deadline, request)
                response.read()
            finally:
                response.close()
        except httpx.TimeoutException as error:
            raise timeout_error(step) from error
        except httpx.LocalProtocolError:
            raise invalid_request_error(step) from None
        except httpx.RequestError as error:
            raise connection_error(step, error) from error
        return read_response(response, step.response_type)


class _DeadlineStream(httpx.SyncByteStream):
    """The body of a sync answer, refused once the attempt's deadline has passed."""

    def __init__(
        self, stream: httpx.SyncByteStream, deadline: float, request: httpx.Request
    ) -> None:
        self._stream = stream
        self._deadline = deadline
        self._request = request

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._stream:
            self._check()
            yield chunk
        self._check()

    def _check(self) -> None:
        if _monotonic() > self._deadline:
            raise httpx.ReadTimeout("The attempt's deadline passed", request=self._request)

    def close(self) -> None:
        self._stream.close()


class AsyncEngine:
    """Runs the request plans of an `AsyncFlashpi` client on an `httpx.AsyncClient`."""

    def __init__(self, config: ClientConfig, http_client: httpx.AsyncClient) -> None:
        self.config = config
        self.http_client = http_client

    async def request(self, spec: RequestSpec[T]) -> APIResponse[T]:
        steps = plan(self.config, spec)
        try:
            step = next(steps)
            while True:
                outcome: object = None
                thrown: FlashpiError | None = None
                try:
                    if isinstance(step, Sleep):
                        await _async_sleep(step.seconds)
                    elif isinstance(step, Fetch):
                        outcome = await self.request(step.spec)
                    else:
                        outcome = await self._send(step)
                except FlashpiError as error:
                    thrown = error
                step = steps.send(outcome) if thrown is None else steps.throw(thrown)
        except StopIteration as stop:
            return cast("APIResponse[T]", stop.value)
        finally:
            steps.close()

    async def _send(self, step: Attempt) -> APIResponse[Any] | APIError:
        """One attempt within its deadline, from sending it to reading the whole answer, as the
        Node SDK's AbortController. Cancelling the task still cancels the attempt."""
        request = self.http_client.build_request(**request_arguments(step))
        try:
            async with asyncio.timeout(step.timeout):
                response = await self.http_client.send(request, follow_redirects=False)
        except (TimeoutError, httpx.TimeoutException) as error:
            raise timeout_error(step) from error
        except httpx.LocalProtocolError:
            raise invalid_request_error(step) from None
        except httpx.RequestError as error:
            raise connection_error(step, error) from error
        return read_response(response, step.response_type)
