"""The error classes, apart from the requests that raise them (see test_retries.py)."""

import json
import pickle
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import pytest

from flashpi import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    FlashpiError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    WebhookVerificationError,
)
from flashpi._errors import api_error, parse_retry_after

PROBLEM = {
    "type": "https://flashpi.com.ec/docs/en/errors/total_mismatch",
    "title": "Problem",
    "status": 422,
    "detail": "Detail of total_mismatch",
    "instance": "/v1/invoices",
    "code": "total_mismatch",
    "errors": [{"field": "items[0].quantity", "code": "out_of_range", "message": "Too big"}],
    "requestId": "req_problem",
    "expectedTotal": "10.00",
}


@pytest.mark.parametrize(
    ("status", "error_class"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (409, ConflictError),
        (413, APIError),
        (422, UnprocessableEntityError),
        (429, RateLimitError),
        (500, InternalServerError),
        (503, InternalServerError),
        (301, APIError),
    ],
)
def test_each_status_gets_its_class(status: int, error_class: type[APIError]) -> None:
    error = api_error(status, httpx.Headers(), "")
    assert type(error) is error_class
    assert isinstance(error, FlashpiError)
    assert error.status == status


def test_reads_the_problem_details_and_their_extensions() -> None:
    headers = httpx.Headers({"x-request-id": "req_header"})
    error = api_error(422, headers, json.dumps(PROBLEM))
    assert error.code == "total_mismatch"
    assert error.title == "Problem"
    assert error.detail == "Detail of total_mismatch"
    assert error.errors == PROBLEM["errors"]
    assert error.request_id == "req_problem"
    assert error.problem is not None
    assert error.problem.get("expectedTotal") == "10.00"
    assert error.message == "422 total_mismatch: Detail of total_mismatch"
    assert str(error) == error.message
    assert error.idempotency_key is None


def test_falls_back_to_the_title_and_the_header_request_id() -> None:
    body = {"code": "rate_limited", "title": "Too many requests", "errors": "not a list"}
    error = api_error(429, httpx.Headers({"x-request-id": "req_1"}), json.dumps(body))
    assert error.message == "429 rate_limited: Too many requests"
    assert error.detail is None
    assert error.errors == []
    assert error.request_id == "req_1"
    assert api_error(400, httpx.Headers(), '{"code": "x"}').message == "400 x"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("<html><body>403 Forbidden</body></html>", "403 <html><body>403 Forbidden</body></html>"),
        ("", "403 (no response body)"),
        ("  \n ", "403 (no response body)"),
        ('{"message": "no code"}', '403 {"message": "no code"}'),
        ("[1, 2]", "403 [1, 2]"),
        ("a\n\n  b" + "c" * 300, "403 a " + "b" + "c" * 197),
    ],
)
def test_describes_bodies_that_are_not_problem_details(body: str, message: str) -> None:
    error = api_error(403, httpx.Headers(), body)
    assert error.code is None
    assert error.problem is None
    assert error.message == message


def test_reads_retry_after_in_seconds_or_as_a_date() -> None:
    now = datetime(2026, 11, 13, 12, 0, 0, tzinfo=UTC).timestamp()
    assert parse_retry_after(None) is None
    assert parse_retry_after("3") == 3
    assert parse_retry_after(" 40000 ") == 40_000
    assert parse_retry_after("Fri, 13 Nov 2026 12:00:02 GMT", now) == 2
    assert parse_retry_after("Fri, 13 Nov 2026 11:59:00 GMT", now) == 0
    assert parse_retry_after("2026-11-13T12:00:01.500Z", now) == 2
    assert parse_retry_after("2026-11-13T12:00:05", now) == 5
    assert parse_retry_after("soon") is None
    assert parse_retry_after("-1") is None
    assert parse_retry_after("1.5") is None
    assert parse_retry_after("٣") is None
    assert parse_retry_after("9" * 5000) == 10**18


def test_reads_retry_after_against_the_clock() -> None:
    later = format_datetime(datetime.now(UTC).replace(microsecond=0), usegmt=True)
    seconds = parse_retry_after(later)
    assert seconds is not None
    assert 0 <= seconds <= 1
    error = api_error(429, httpx.Headers({"retry-after": "7"}), "")
    assert error.retry_after == 7
    assert api_error(429, httpx.Headers(), "").retry_after is None


def test_the_errors_survive_pickling() -> None:
    error = api_error(422, httpx.Headers({"x-request-id": "req_1"}), json.dumps(PROBLEM))
    error.idempotency_key = "order-42"
    copy = pickle.loads(pickle.dumps(error))  # noqa: S301
    assert type(copy) is UnprocessableEntityError
    assert copy.message == error.message
    assert str(copy) == str(error)
    assert copy.problem == error.problem
    assert copy.headers["x-request-id"] == "req_1"
    assert copy.idempotency_key == "order-42"

    webhook = pickle.loads(pickle.dumps(WebhookVerificationError("invalid_secret", "Bad")))  # noqa: S301
    assert webhook.reason == "invalid_secret"
    assert str(webhook) == "Bad"

    timeout = pickle.loads(pickle.dumps(APITimeoutError("GET / timed out")))  # noqa: S301
    assert isinstance(timeout, APIConnectionError)
    assert timeout.idempotency_key is None
