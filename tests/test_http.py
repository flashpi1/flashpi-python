"""The pure parts of the request logic, shared by both clients."""

from typing import Any

import httpx
import pytest

import flashpi._http as http_module
from flashpi import APIConnectionError, APITimeoutError, FlashpiError
from flashpi._errors import api_error
from flashpi._http import (
    ClientConfig,
    Multipart,
    RequestSpec,
    backoff,
    build_headers,
    build_url,
    path_of,
    retry_delay,
)
from flashpi._response import async_response_wrapper, response_wrapper

TEST_KEY = f"fp_test_{'a' * 48}"

pytestmark = pytest.mark.anyio


def config(**changes: Any) -> ClientConfig:
    settings: dict[str, Any] = {
        "api_key": TEST_KEY,
        "base_url": "https://api.flashpi.com.ec",
        "timeout": 60.0,
        "max_retries": 2,
        "language": None,
        "default_headers": {},
        **changes,
    }
    return ClientConfig(**settings)


class TestPathOf:
    def test_encodes_each_id_like_encode_uri_component(self) -> None:
        assert path_of("/v1/issuers/{}", "a/b?c") == "/v1/issuers/a%2Fb%3Fc"
        assert path_of("/v1/a/{}/b/{}", "x y", "ñ") == "/v1/a/x%20y/b/%C3%B1"
        assert path_of("/v1/a/{}", "-_.!~*'()") == "/v1/a/-_.!~*'()"
        assert path_of("/v1/status") == "/v1/status"

    def test_refuses_missing_and_dot_segment_ids(self) -> None:
        with pytest.raises(FlashpiError, match=r"Missing id in /v1/a/\{id\}: got ''"):
            path_of("/v1/a/{}", "")
        with pytest.raises(FlashpiError, match="got None"):
            path_of("/v1/a/{}", None)  # pyright: ignore[reportArgumentType]
        with pytest.raises(FlashpiError, match=r"Invalid id in /v1/a/\{id\}: '\.\.'"):
            path_of("/v1/a/{}", "..")

    def test_refuses_a_template_that_does_not_match_the_ids(self) -> None:
        with pytest.raises(ValueError, match="1 placeholders, not 2"):
            path_of("/v1/a/{}", "x", "y")


class TestBuildUrl:
    def test_leaves_none_out_and_writes_booleans_as_json(self) -> None:
        query = {"a": None, "b": True, "c": False, "d": 3, "e": "x y"}
        assert build_url("https://h/", "/v1/x", query) == "https://h/v1/x?b=true&c=false&d=3&e=x+y"
        assert build_url("https://h//", "/v1/x", {"a": None}) == "https://h/v1/x"
        assert build_url("https://h", "/v1/x", None) == "https://h/v1/x"


class TestBuildHeaders:
    def test_applies_the_settings_from_the_lowest_priority_to_the_highest(self) -> None:
        settings = config(language="es", default_headers={"Accept": "text/plain", "X-Team": "a"})
        spec = RequestSpec[Any](method="POST", path="/", body={})
        options: http_module.RequestOptions = {
            "language": "en",
            "extra_headers": {"x-team": "b", "Content-Type": "text/plain", "user-agent": "mine"},
            "correlation_id": "c-1",
        }
        headers = build_headers(settings, spec, options, "key-1")
        assert dict(headers) == {
            "accept": "text/plain",
            "user-agent": "mine",
            "accept-language": "en",
            "x-team": "b",
            "content-type": "application/json",
            "x-correlation-id": "c-1",
            "idempotency-key": "key-1",
            "authorization": f"Bearer {TEST_KEY}",
        }

    def test_leaves_the_content_type_of_a_multipart_body_to_httpx(self) -> None:
        multipart = Multipart(fields={}, files={})
        spec = RequestSpec[Any](method="POST", path="/", multipart=multipart, body={"ignored": 1})
        options: http_module.RequestOptions = {"extra_headers": {"content-type": "text/plain"}}
        headers = build_headers(config(), spec, options, None)
        assert "content-type" not in headers
        assert "idempotency-key" not in headers

    def test_never_shows_the_key_in_a_repr(self) -> None:
        headers = build_headers(config(), RequestSpec[Any](method="GET", path="/"), {}, None)
        assert TEST_KEY not in repr(headers)
        assert TEST_KEY not in repr(config())


class TestRetryDelay:
    def test_backs_off_from_half_a_second_to_8_seconds_with_up_to_25_percent_of_jitter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(http_module, "_random", lambda: 0.0)
        assert [backoff(retries) for retries in range(6)] == [0.5, 1, 2, 4, 8, 8]
        assert backoff(10_000) == 8
        monkeypatch.setattr(http_module, "_random", lambda: 0.999)
        assert backoff(0) == pytest.approx(0.375, abs=0.001)
        assert backoff(4) == pytest.approx(6.002, abs=0.001)

    def test_decides_what_to_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(http_module, "_random", lambda: 0.0)

        def delay(
            status: int, code: str | None = None, retry_after: str | None = None
        ) -> float | None:
            body = f'{{"code": "{code}"}}' if code else ""
            headers = httpx.Headers({"retry-after": retry_after} if retry_after else {})
            return retry_delay(api_error(status, headers, body), 0)

        assert retry_delay(APIConnectionError("x"), 1) == 1
        assert retry_delay(APITimeoutError("x"), 2) == 2
        assert retry_delay(FlashpiError("not JSON"), 0) is None
        assert delay(408) == 0.5
        assert delay(429) == 0.5
        assert delay(429, retry_after="60") == 60
        assert delay(429, retry_after="61") is None
        assert delay(429, retry_after="0") == 0
        assert delay(500) == 0.5
        assert delay(501) is None
        assert delay(503, "demo_issuer_unavailable") is None
        assert delay(409, "idempotency_key_in_progress") == 1
        assert delay(409, "sequential_already_used") is None
        assert delay(400) is None
        assert delay(404) is None
        assert delay(422) is None


class TestWithResponse:
    def test_refuses_a_call_that_sent_no_request(self) -> None:
        with pytest.raises(FlashpiError, match="sent no request"):
            response_wrapper(path_of)("/v1/a/{}", "x")

    async def test_refuses_an_async_call_that_sent_no_request(self) -> None:
        async def nothing() -> int:
            return 1

        with pytest.raises(FlashpiError, match="sent no request"):
            await async_response_wrapper(nothing)()
