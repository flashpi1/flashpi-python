"""Regression tests for the core findings of the Node SDK's reviews (Node:
test/review-fixes.test.ts). The webhook ones are in test_webhooks.py."""

import re

import httpx
import pytest

from flashpi import APIConnectionError, APIError, APITimeoutError, ConflictError, FlashpiError
from tests.conftest import MakeApi
from tests.support import (
    ID,
    OTHER_ID,
    Clock,
    document_body,
    json_response,
    problem,
    sent_json,
    timeout_after,
)

pytestmark = pytest.mark.anyio


def in_progress() -> httpx.Response:
    return problem(409, "idempotency_key_in_progress")


class TestAnEarlierAttemptStillRunning:
    async def test_waits_for_it_with_the_same_key_without_using_up_the_retries(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(
            httpx.ConnectError("socket hang up"),
            *(in_progress() for _ in range(5)),
            json_response(document_body(ID, "authorized"), 200, {"idempotent-replayed": "true"}),
        )
        body = {"options": {"waitForAuthorization": True, "waitTimeoutSeconds": 30}}
        document = await api.call("issue", body)
        assert (document["id"], document["status"]) == (ID, "authorized")
        assert len(api.sent) == 7
        assert len({request.headers["idempotency-key"] for request in api.sent}) == 1
        # 0.5 s backoff after the network error, then 1 + 2 + 4 + 5 + 5 s of waiting.
        assert clock.sleeps == [0.5, 1, 2, 4, 5, 5]
        assert clock.elapsed == 17.5

    async def test_stops_when_the_calls_time_is_up_and_hands_back_the_key(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(
            httpx.ConnectError("socket hang up"),
            *(in_progress() for _ in range(20)),
            timeout=10,
        )
        with pytest.raises(ConflictError) as caught:
            await api.call("issue", {})
        assert caught.value.code == "idempotency_key_in_progress"
        assert caught.value.idempotency_key == api.sent[0].headers["idempotency-key"]
        assert clock.elapsed <= 10
        assert len(api.sent) > 3

    async def test_follows_the_normal_retry_rules_on_the_first_attempt(self, make: MakeApi) -> None:
        api = make(*(in_progress() for _ in range(4)))
        with pytest.raises(ConflictError):
            await api.call("issue", {}, idempotency_key="order-1", max_retries=0)
        assert len(api.sent) == 1

    async def test_recovers_the_document_if_the_wait_ends_in_idempotency_key_reused(
        self, make: MakeApi
    ) -> None:
        api = make(
            httpx.ConnectError("socket hang up"),
            in_progress(),
            problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}),
            json_response(document_body(OTHER_ID, "authorized")),
        )
        assert (await api.call("issue", {}))["id"] == OTHER_ID
        assert api.sent[-1].url.path == f"/v1/documents/{OTHER_ID}"

    async def test_retries_normally_when_the_attempt_timed_out_with_the_time_spent(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(
            timeout_after(clock, 10),
            in_progress(),
            json_response(document_body(), 202),
            timeout=10,
        )
        assert (await api.call("issue", {}))["id"] == ID
        assert len(api.sent) == 3
        assert clock.sleeps == [0.5, 1]

    async def test_does_not_wait_on_another_processs_attempt_even_after_its_first_409(
        self, make: MakeApi
    ) -> None:
        api = make(in_progress(), in_progress(), in_progress(), json_response({}, 202))
        with pytest.raises(ConflictError):
            await api.call("issue", {}, idempotency_key="order-1")
        assert len(api.sent) == 3

    async def test_waits_after_a_5xx_without_problem_details(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(
            httpx.Response(502, content=b"<html>502 Bad Gateway</html>"),
            in_progress(),
            in_progress(),
            in_progress(),
            json_response(document_body(), 202),
        )
        assert (await api.call("issue", {}))["id"] == ID
        assert len(api.sent) == 5
        assert clock.sleeps == [0.5, 1, 2, 4]

    async def test_does_not_wait_after_a_5xx_with_problem_details(self, make: MakeApi) -> None:
        api = make(problem(500, "internal_error"), in_progress(), in_progress())
        with pytest.raises(ConflictError):
            await api.call("issue", {})
        assert len(api.sent) == 3


class TestTheIdempotencyKeyOnErrors:
    async def test_is_on_the_api_connection_and_timeout_errors_of_a_post(
        self, make: MakeApi, clock: Clock
    ) -> None:
        api = make(problem(422, "validation_failed"))
        with pytest.raises(APIError) as api_error:
            await api.call("issue", {})
        assert api_error.value.idempotency_key == api.sent[0].headers["idempotency-key"]

        network = make(httpx.ConnectError("x"), max_retries=0)
        with pytest.raises(APIConnectionError) as connection:
            await network.call("create", {})
        assert connection.value.idempotency_key is not None
        assert re.fullmatch(r"[0-9a-f-]{36}", connection.value.idempotency_key)

        slow = make(timeout_after(clock, 1), max_retries=0, timeout=1)
        with pytest.raises(APITimeoutError) as timeout:
            await slow.call("issue", {}, idempotency_key="order-7")
        assert timeout.value.idempotency_key == "order-7"

    async def test_is_on_a_body_that_is_not_json(self, make: MakeApi) -> None:
        api = make(httpx.Response(201, content=b"<html>"))
        with pytest.raises(FlashpiError, match="not JSON") as caught:
            await api.call("create", {}, idempotency_key="order-8")
        assert caught.value.idempotency_key == "order-8"

    async def test_is_not_set_on_errors_of_other_methods(self, make: MakeApi) -> None:
        api = make(problem(404, "not_found"))
        with pytest.raises(APIError) as caught:
            await api.call("get", ID)
        assert caught.value.idempotency_key is None

    async def test_comes_from_an_idempotency_key_header_too_on_every_attempt(
        self, make: MakeApi
    ) -> None:
        api = make(problem(503, "x"), json_response({}, 201))
        await api.call("create", {}, extra_headers={"Idempotency-Key": "order-42"})
        assert [request.headers["idempotency-key"] for request in api.sent] == ["order-42"] * 2

    async def test_prefers_the_option_over_the_header(self, make: MakeApi) -> None:
        api = make(json_response({}, 201))
        options = {"idempotency_key": "option", "extra_headers": {"idempotency-key": "header"}}
        await api.call("create", {}, **options)
        assert api.sent[0].headers.get_list("idempotency-key") == ["option"]

    async def test_stays_on_the_error_when_the_recovered_document_cannot_be_read(
        self, make: MakeApi
    ) -> None:
        api = make(
            httpx.ConnectError("reset"),
            problem(422, "idempotency_key_reused", {"documentId": OTHER_ID}),
            httpx.ConnectError("reset"),
            httpx.ConnectError("reset"),
            httpx.ConnectError("reset"),
        )
        with pytest.raises(APIConnectionError) as caught:
            await api.call("issue", {})
        assert caught.value.idempotency_key == api.sent[0].headers["idempotency-key"]
        assert len(api.sent) == 5

    async def test_stays_on_the_error_when_the_recovered_id_is_not_a_path_id(
        self, make: MakeApi
    ) -> None:
        api = make(
            httpx.ConnectError("reset"),
            problem(422, "idempotency_key_reused", {"documentId": ".."}),
        )
        with pytest.raises(FlashpiError, match="Invalid id") as caught:
            await api.call("issue", {}, idempotency_key="order-9")
        assert caught.value.idempotency_key == "order-9"
        assert len(api.sent) == 2


async def test_sends_the_same_body_on_a_retry_when_the_caller_changes_the_object(
    make: MakeApi,
) -> None:
    body = {"items": [{"code": "A"}]}

    def change_then_fail(request: httpx.Request) -> httpx.Response:
        body["items"][0] = {"code": "B"}
        raise httpx.ConnectError("reset", request=request)

    api = make(change_then_fail, json_response(document_body(), 202))
    await api.call("issue", body)
    assert sent_json(api.sent[0]) == {"items": [{"code": "A"}]}
    assert sent_json(api.sent[1]) == {"items": [{"code": "A"}]}


class TestIdsThatAreDotSegments:
    @pytest.mark.parametrize("value", [".", ".."])
    async def test_refuses_them_before_sending_anything(self, make: MakeApi, value: str) -> None:
        api = make()
        with pytest.raises(FlashpiError, match="Invalid id"):
            await api.call("delete", value)
        with pytest.raises(FlashpiError, match="Invalid id"):
            await api.call("get_nested", ID, value)
        assert api.sent == []

    async def test_sends_ids_that_only_contain_dots_encoded(self, make: MakeApi) -> None:
        api = make(json_response({}), json_response({}))
        await api.call("get", "...")
        await api.call("get", "%2e%2e")
        assert [request.url.raw_path for request in api.sent] == [
            b"/v1/things/...",
            b"/v1/things/%252e%252e",
        ]


class TestOptions:
    async def test_lets_the_request_language_win_over_a_client_accept_language_header(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}), default_headers={"Accept-Language": "es"})
        await api.call("status", language="en")
        assert api.sent[0].headers.get_list("accept-language") == ["en"]

    async def test_lets_request_headers_win_over_the_request_language(self, make: MakeApi) -> None:
        api = make(json_response({}))
        await api.call("status", language="en", extra_headers={"accept-language": "es"})
        assert api.sent[0].headers["accept-language"] == "es"

    @pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), 2**31, True])
    async def test_rejects_a_request_timeout_before_sending(
        self, make: MakeApi, timeout: float
    ) -> None:
        api = make(json_response({}))
        with pytest.raises(FlashpiError, match="timeout"):
            await api.call("status", timeout=timeout)
        assert api.sent == []

    @pytest.mark.parametrize("max_retries", [-1, 1.5, float("nan"), False])
    async def test_rejects_request_max_retries(self, make: MakeApi, max_retries: float) -> None:
        api = make(json_response({}))
        with pytest.raises(FlashpiError, match="max_retries"):
            await api.call("status", max_retries=max_retries)
        assert api.sent == []

    async def test_accepts_explicit_none_options_as_the_defaults(self, make: MakeApi) -> None:
        api = make(json_response({}, 201))
        options = {
            "timeout": None,
            "max_retries": None,
            "idempotency_key": None,
            "language": None,
            "correlation_id": None,
            "extra_headers": None,
        }
        assert await api.call("create", {}, **options) == {}
        assert "x-correlation-id" not in api.sent[0].headers

    async def test_raises_the_timeout_of_a_sync_issue_to_its_wait_plus_15_seconds(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}, 200), json_response({}, 200), timeout=5)
        await api.call("issue", {"options": {"waitForAuthorization": True}})
        await api.call("issue", {"options": {"waitForAuthorization": True}}, timeout=60)
        assert api.sent[0].extensions["timeout"]["read"] == 30
        assert api.sent[1].extensions["timeout"]["read"] == 60
