"""The errors this package raises."""

from __future__ import annotations

import json
import math
import re
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal, TypeAlias, cast

import httpx

from .types import ApiErrorCode, FieldError, Problem

WebhookVerificationReason: TypeAlias = Literal[
    "missing_headers",
    "invalid_timestamp",
    "timestamp_out_of_range",
    "no_matching_signature",
    "invalid_secret",
    "invalid_payload",
]
"""Why a webhook was rejected by `verify_webhook_signature()` or `unwrap_webhook()`."""


class FlashpiError(Exception):
    """Every error this package raises extends this class.

    Except for invalid arguments (TypeError and ValueError, as for any Python function) and the
    cancellation of an async call, which raises `asyncio.CancelledError` as usual.
    """

    message: str
    """What went wrong."""

    idempotency_key: str | None
    """The Idempotency-Key a failed POST used (the caller's or the one the SDK made). To try the
    same operation again later without issuing twice, pass it back:
    `create(body, idempotency_key=error.idempotency_key)`."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
        self.idempotency_key = None

    def __reduce__(self) -> tuple[Any, ...]:
        # Rebuilt from its state, so the errors survive pickling (Celery, multiprocessing).
        return (_restore, (type(self), self.args, self.__dict__))


def _restore(cls: type[FlashpiError], args: tuple[Any, ...], state: dict[str, Any]) -> FlashpiError:
    error = cls.__new__(cls)
    error.args = args
    error.__dict__.update(state)
    return error


class APIError(FlashpiError):
    """The API answered with an error status.

    Branch on `code` (stable English slugs such as `validation_failed`), never on `message`, which
    follows the requested language.
    """

    status: int
    """HTTP status of the answer."""

    code: ApiErrorCode | None
    """Error code, or None when the answer had no Problem Details (for example a 502)."""

    title: str | None
    """Short summary of the problem type."""

    detail: str | None
    """What went wrong in this request."""

    errors: list[FieldError]
    """Field-level problems of a request body or query (may be empty)."""

    request_id: str | None
    """Flashpi's id of the request (`x-request-id`): share it with support."""

    problem: Problem | None
    """The full Problem Details body, with its extension members, when there was one."""

    headers: httpx.Headers
    """Response headers."""

    def __init__(
        self,
        status: int,
        headers: httpx.Headers,
        problem: Problem | None,
        body_text: str = "",
    ) -> None:
        super().__init__(_error_message(status, problem, body_text))
        self.status = status
        self.headers = headers
        self.problem = problem
        members: dict[str, object] = cast("dict[str, object]", problem or {})
        code = members.get("code")
        self.code = code if isinstance(code, str) else None
        title = members.get("title")
        self.title = title if isinstance(title, str) else None
        detail = members.get("detail")
        self.detail = detail if isinstance(detail, str) else None
        errors = members.get("errors")
        self.errors = cast("list[FieldError]", errors) if isinstance(errors, list) else []
        request_id = members.get("requestId")
        self.request_id = request_id if isinstance(request_id, str) else headers.get("x-request-id")

    @property
    def retry_after(self) -> int | None:
        """Seconds the API asked to wait before trying again (`Retry-After`), or None.

        Daily quota errors point at the next midnight in Ecuador, so this can be hours.
        """
        return parse_retry_after(self.headers.get("retry-after"))


class BadRequestError(APIError):
    """400: the request could not be read (malformed JSON, invalid Idempotency-Key, ...)."""


class AuthenticationError(APIError):
    """401: the API key is missing, malformed, unknown or revoked."""


class PermissionDeniedError(APIError):
    """403: the key may not do this (read-only, another issuer, IP allowlist, suspended account)."""


class NotFoundError(APIError):
    """404: the resource does not exist in this mode (test or live) for this account."""


class ConflictError(APIError):
    """409: the request conflicts with the current state (sequential used, RIDE not ready, ...)."""


class UnprocessableEntityError(APIError):
    """422: the request is well formed but invalid (`validation_failed`, `total_mismatch`, ...)."""


class RateLimitError(APIError):
    """429: a limit was reached; see `retry_after` and the `limit` and `resetsAt` members."""


class InternalServerError(APIError):
    """5xx: Flashpi failed to answer. Requests are retried automatically before this is raised."""


class APIConnectionError(FlashpiError):
    """The request never got an answer (DNS, TLS, connection reset, ...)."""


class APITimeoutError(APIConnectionError):
    """The request took longer than the `timeout` option."""


class WebhookVerificationError(FlashpiError):
    """A webhook did not come from Flashpi, was altered, or is too old: answer 400 and ignore it."""

    reason: WebhookVerificationReason
    """Why it was rejected."""

    def __init__(self, reason: WebhookVerificationReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason


_ERROR_CLASSES: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}


def api_error(status: int, headers: httpx.Headers, body_text: str) -> APIError:
    """The error subclass that matches the status of an answer."""
    error_class = _ERROR_CLASSES.get(status, InternalServerError if status >= 500 else APIError)
    return error_class(status, headers, _parse_problem(body_text), body_text)


def _parse_problem(body_text: str) -> Problem | None:
    if not body_text:
        return None
    try:
        parsed: object = json.loads(body_text)
    except (ValueError, RecursionError):
        # Not JSON: an answer from the edge (CDN or firewall), not from the API.
        return None
    if isinstance(parsed, dict) and isinstance(cast("dict[str, object]", parsed).get("code"), str):
        return cast("Problem", parsed)
    return None


def _error_message(status: int, problem: Problem | None, body_text: str) -> str:
    if problem is not None:
        members = cast("dict[str, object]", problem)
        detail = members.get("detail")
        if not isinstance(detail, str):
            detail = members.get("title")
        code = members.get("code")
        return f"{status} {code}: {detail}" if isinstance(detail, str) else f"{status} {code}"
    excerpt = " ".join(body_text.split())[:200]
    return f"{status} {excerpt}" if excerpt else f"{status} (no response body)"


_DELTA_SECONDS = re.compile(r"[0-9]+")
# Longer digit strings are past any useful wait (and past int()'s digit limit).
_MAX_DELTA_DIGITS = 18


def parse_retry_after(value: str | None, now: float | None = None) -> int | None:
    """Seconds from a `Retry-After` value (delta-seconds or an HTTP date), or None.

    `now` is the current Unix time in seconds (default: the clock).
    """
    if value is None:
        return None
    trimmed = value.strip()
    if _DELTA_SECONDS.fullmatch(trimmed):
        return int(trimmed) if len(trimmed) <= _MAX_DELTA_DIGITS else 10**_MAX_DELTA_DIGITS
    moment = _parse_date(trimmed)
    if moment is None:
        return None
    current = time.time() if now is None else now
    return max(0, math.ceil(moment - current))


def _parse_date(value: str) -> float | None:
    """Unix seconds of an HTTP date (or an ISO 8601 one), or None."""
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()
