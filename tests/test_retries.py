"""Errors, retries and recoveries (Node: test/retries.test.ts)."""

from datetime import UTC, datetime, timedelta
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
)
from tests.conftest import MakeApi
from tests.support import (
    ID,
    OTHER_ID,
    Clock,
    document_body,
    json_response,
    problem,
    timeout_after,
)

pytestmark = pytest.mark.anyio


def network_error() -> httpx.ConnectError:
    return httpx.ConnectError("fetch failed")


class TestErrors:
    @pytest.mark.parametrize(
        ("status", "code", "error_class"),
        [
            (400, "malformed_json", BadRequestError),
            (401, "invalid_api_key", AuthenticationError),
            (403, "key_read_only", PermissionDeniedError),
            (404, "not_found", NotFoundError),
            (409, "sequential_already_used", ConflictError),
            (413, "payload_too_large", APIError),
            (422, "validation_failed", UnprocessableEntityError),
        ],
    )
    async def test_maps_the_status_to_its_class_and_does_not_retry_it(
        self, make: MakeApi, status: int, code: str, error_class: type[APIError]
    ) -> None:
        api = make(problem(status, code))
        with pytest.raises(error_class) as caught:
            await api.call("issue", {})
        assert isinstance(caught.value, APIError)
        assert isinstance(caught.value, FlashpiError)
        assert len(api.sent) == 1

    async def test_exposes_the_problem_details_members_and_extensions(self, make: MakeApi) -> None:
        errors = [{"field": "items[0].quantity", "code": "out_of_range", "message": "Too big"}]
        extra = {"errors": errors, "expectedTotal": "10.00", "computedTotal": "11.50"}
        api = make(problem(422, "total_mismatch", extra))
        with pytest.raises(UnprocessableEntityError) as caught:
            await api.call("issue", {})
        error = caught.value
        assert error.status == 422
        assert error.code == "total_mismatch"
        assert error.title == "Problem"
        assert error.detail == "Detail of total_mismatch"
        assert error.request_id == "req_problem"
        assert error.errors == errors
        assert error.message == "422 total_mismatch: Detail of total_mismatch"
        assert error.problem is not None
        assert error.problem.get("expectedTotal") == "10.00"
        assert "problem+json" in error.headers["content-type"]

    async def test_handles_an_error_body_that_is_not_problem_details(self, make: MakeApi) -> None:
        body = b"<html><body>403 Forbidden</body></html>"
        api = make(httpx.Response(403, content=body, headers={"x-request-id": "edge_1"}))
        with pytest.raises(PermissionDeniedError) as caught:
            await api.call("status")
        error = caught.value
        assert (error.code, error.detail, error.errors, error.request_id) == (
            None,
            None,
            [],
            "edge_1",
        )
        assert str(error) == "403 <html><body>403 Forbidden</body></html>"

    async def test_describes_an_empty_error_body(self, make: MakeApi) -> None:
        api = make(httpx.Response(404))
        with pytest.raises(NotFoundError, match=r"^404 \(no response body\)$"):
            await api.call("status")

    async def test_treats_a_redirect_as_an_error_without_following_it(self, make: MakeApi) -> None:
        api = make(httpx.Response(301, headers={"location": "https://example.com/"}))
        with pytest.raises(APIError) as caught:
            await api.call("status")
        assert caught.value.status == 301
        assert len(api.sent) == 1


class TestRetries:
    async def test_retries_a_500_with_the_same_key_waiting_half_a_second_then_one(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(
            problem(500, "internal_error"),
            problem(502, "internal_error"),
            json_response(document_body(), 202),
        )
        assert (await api.call("issue", {}))["id"] == ID
        assert len(api.sent) == 3
        assert len({request.headers["idempotency-key"] for request in api.sent}) == 1
        assert clock.elapsed == 1.5

    async def test_raises_the_last_error_once_the_retries_run_out(self, make: MakeApi) -> None:
        api = make(*(problem(503, "service_unavailable") for _ in range(3)))
        with pytest.raises(InternalServerError):
            await api.call("status")
        assert len(api.sent) == 3

    async def test_honors_max_retries_of_the_client_and_of_the_request(self, make: MakeApi) -> None:
        first = make(problem(500, "internal_error"), max_retries=0)
        with pytest.raises(InternalServerError):
            await first.call("status")
        assert len(first.sent) == 1

        second = make(problem(500, "internal_error"), json_response({}), max_retries=0)
        assert await second.call("status", max_retries=1) == {}
        assert len(second.sent) == 2

    async def test_retries_network_errors_and_wraps_the_last_one(self, make: MakeApi) -> None:
        api = make(network_error(), network_error(), network_error())
        with pytest.raises(APIConnectionError) as caught:
            await api.call("get", ID)
        assert "fetch failed" in str(caught.value)
        assert str(caught.value).startswith(f"GET https://api.flashpi.com.ec/v1/things/{ID} failed")
        assert isinstance(caught.value.__cause__, httpx.ConnectError)
        assert len(api.sent) == 3

    async def test_times_out_a_slow_attempt_and_retries_it(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(timeout_after(clock, 1), json_response({"ok": True}), timeout=1)
        assert await api.call("status") == {"ok": True}
        assert len(api.sent) == 2
        assert clock.elapsed == 1.5

    async def test_raises_a_timeout_error_when_every_attempt_times_out(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(timeout_after(clock, 2), timeout=2, max_retries=0)
        with pytest.raises(APITimeoutError, match="timed out after 2 seconds") as caught:
            await api.call("status")
        assert isinstance(caught.value, APIConnectionError)

    async def test_sends_the_timeout_of_each_attempt_to_httpx(self, make: MakeApi) -> None:
        api = make(json_response({}), json_response({}), timeout=7.5)
        await api.call("status")
        await api.call("status", timeout=2)
        timeouts = [request.extensions["timeout"] for request in api.sent]
        assert timeouts[0] == {"connect": 7.5, "read": 7.5, "write": 7.5, "pool": 7.5}
        assert timeouts[1]["read"] == 2

    async def test_waits_a_short_retry_after_of_a_429(self, make: MakeApi, clock: Clock) -> None:
        api = make(problem(429, "rate_limited", headers={"retry-after": "3"}), json_response({}))
        await api.call("status")
        assert len(api.sent) == 2
        assert clock.elapsed == 3

    async def test_does_not_wait_for_a_daily_quota_and_reports_when_it_resets(
        self, make: MakeApi
    ) -> None:
        extra = {"limit": 50, "resetsAt": "2026-11-13T05:00:00.000Z"}
        quota = problem(429, "demo_issuer_quota_exceeded", extra, {"retry-after": "40000"})
        api = make(quota)
        with pytest.raises(RateLimitError) as caught:
            await api.call("issue", {})
        assert caught.value.retry_after == 40_000
        assert caught.value.problem is not None
        assert caught.value.problem.get("limit") == 50
        assert len(api.sent) == 1

    async def test_reads_a_retry_after_given_as_an_http_date(self, make: MakeApi) -> None:
        at = format_datetime(datetime.now(UTC) + timedelta(seconds=2), usegmt=True)
        api = make(problem(503, "x", headers={"retry-after": at}), json_response({}))
        await api.call("status")
        assert len(api.sent) == 2

    async def test_retries_a_409_in_progress_after_at_least_a_second(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(
            problem(409, "idempotency_key_in_progress"),
            json_response(document_body(), 202, {"idempotent-replayed": "true"}),
        )
        assert (await api.call("issue", {}))["id"] == ID
        assert len(api.sent) == 2
        assert clock.elapsed == 1

    async def test_does_not_retry_the_missing_demo_certificate(self, make: MakeApi) -> None:
        api = make(problem(503, "demo_issuer_unavailable"))
        with pytest.raises(InternalServerError):
            await api.call("issue", {})
        assert len(api.sent) == 1

    async def test_does_not_retry_a_501(self, make: MakeApi) -> None:
        api = make(httpx.Response(501))
        with pytest.raises(InternalServerError):
            await api.call("status")
        assert len(api.sent) == 1

    async def test_retries_a_408(self, make: MakeApi) -> None:
        api = make(httpx.Response(408), json_response({}))
        assert await api.call("status") == {}

    async def test_caps_the_backoff_at_8_seconds(self, make: MakeApi, clock: Clock) -> None:
        replies = [problem(500, "internal_error") for _ in range(6)]
        api = make(*replies, json_response({}), max_retries=6)
        await api.call("status")
        assert clock.sleeps == [0.5, 1, 2, 4, 8, 8]
        assert clock.elapsed == 23.5

    async def test_retries_patch_and_delete_too(self, make: MakeApi) -> None:
        api = make(network_error(), json_response({}), network_error(), httpx.Response(204))
        assert await api.call("update", ID, {"name": "x"}) == {}
        assert await api.call("delete", ID) is None
        assert [request.method for request in api.sent] == ["PATCH", "PATCH", "DELETE", "DELETE"]


class TestRecoveringADocumentCreatedByAnEarlierAttempt:
    async def test_returns_the_document_when_a_retry_finds_its_key_used_by_it(
        self, make: MakeApi
    ) -> None:
        api = make(
            problem(500, "internal_error"),
            problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}),
            json_response(document_body(OTHER_ID, "authorized")),
        )
        document = await api.call("issue", {}, language="es", correlation_id="order-1")
        assert (document["id"], document["status"]) == (OTHER_ID, "authorized")
        assert [f"{request.method} {request.url.path}" for request in api.sent] == [
            "POST /v1/invoices",
            "POST /v1/invoices",
            f"GET /v1/documents/{OTHER_ID}",
        ]
        read = api.sent[2]
        assert "idempotency-key" not in read.headers
        assert read.headers["accept-language"] == "es"
        assert read.headers["x-correlation-id"] == "order-1"

    async def test_returns_the_reads_response_with_with_response(self, make: MakeApi) -> None:
        api = make(
            httpx.ConnectError("reset"),
            problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}),
            json_response(document_body(OTHER_ID), 200, {"x-request-id": "req_read"}),
        )
        result = await api.call_with_response("issue", {})
        assert result.data["id"] == OTHER_ID
        assert result.request_id == "req_read"
        assert result.response.request.method == "GET"

    async def test_raises_the_reuse_on_the_first_attempt(self, make: MakeApi) -> None:
        api = make(problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}))
        with pytest.raises(UnprocessableEntityError) as caught:
            await api.call("issue", {}, idempotency_key="used-before")
        assert caught.value.code == "idempotency_key_reused"
        assert caught.value.idempotency_key == "used-before"
        assert len(api.sent) == 1

    @pytest.mark.parametrize("extra", [{}, {"documentId": ""}, {"documentId": 7}])
    async def test_raises_a_reuse_without_a_document_id(
        self, make: MakeApi, extra: dict[str, object]
    ) -> None:
        api = make(network_error(), problem(422, "idempotency_key_reused", extra))
        with pytest.raises(UnprocessableEntityError):
            await api.call("issue", {})
        assert len(api.sent) == 2

    async def test_does_not_apply_to_other_posts(self, make: MakeApi) -> None:
        api = make(
            problem(500, "internal_error"),
            problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}),
        )
        with pytest.raises(UnprocessableEntityError):
            await api.call("create", {})
        assert len(api.sent) == 2


class TestDeleteRetriedAfterALostAnswer:
    async def test_treats_a_404_on_a_retry_as_done(self, make: MakeApi) -> None:
        api = make(httpx.ConnectError("socket hang up"), problem(404, "not_found"))
        assert await api.call("delete", ID) is None
        assert len(api.sent) == 2

    async def test_answers_with_a_204_built_from_the_404(self, make: MakeApi) -> None:
        api = make(httpx.ConnectError("socket hang up"), problem(404, "not_found"))
        result = await api.call_with_response("delete", ID)
        assert result.data is None
        assert result.response.status_code == 204
        assert result.response.content == b""
        assert "content-type" not in result.response.headers
        assert result.response.request.method == "DELETE"
        assert result.request_id == "req_problem"

    async def test_raises_a_404_on_the_first_attempt(self, make: MakeApi) -> None:
        api = make(problem(404, "not_found"))
        with pytest.raises(NotFoundError):
            await api.call("delete", ID)
