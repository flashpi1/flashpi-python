"""The clients and the requests they send (Node: test/client.test.ts)."""

import re

import httpx
import pytest

from flashpi import (
    DEFAULT_BASE_URL,
    VERSION,
    APIResponse,
    AsyncFlashpi,
    Flashpi,
    FlashpiError,
)
from tests.conftest import MakeApi
from tests.support import ID, LIVE_KEY, TEST_KEY, json_response

pytestmark = pytest.mark.anyio

CLIENTS = [Flashpi, AsyncFlashpi]
UUID = re.compile(r"[0-9a-f-]{36}")


@pytest.fixture(autouse=True)
def no_key_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLASHPI_API_KEY", raising=False)


@pytest.mark.parametrize("client_class", CLIENTS)
class TestTheClient:
    def test_takes_the_key_and_tells_the_environment_from_its_prefix(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        assert client_class(TEST_KEY).environment == "test"
        assert client_class(api_key=LIVE_KEY).environment == "live"

    def test_falls_back_to_the_environment_variable(
        self, client_class: type[Flashpi | AsyncFlashpi], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FLASHPI_API_KEY", LIVE_KEY)
        assert client_class().environment == "live"
        assert client_class(timeout=1).environment == "live"
        assert client_class(TEST_KEY).environment == "test"

    def test_refuses_a_missing_key(
        self, client_class: type[Flashpi | AsyncFlashpi], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with pytest.raises(FlashpiError, match="Missing API key"):
            client_class()
        monkeypatch.setenv("FLASHPI_API_KEY", "  ")
        with pytest.raises(FlashpiError, match="Missing API key"):
            client_class()
        with pytest.raises(FlashpiError, match="Missing API key"):
            client_class(" \n")

    def test_refuses_a_webhook_secret_or_another_prefix(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        with pytest.raises(FlashpiError, match="webhook signing secret"):
            client_class("whsec_abc")
        with pytest.raises(FlashpiError, match="fp_test_ or fp_live_"):
            client_class("sk_test_123")

    @pytest.mark.parametrize(
        ("options", "message"),
        [
            ({"timeout": 0}, "timeout"),
            ({"timeout": -1}, "timeout"),
            ({"timeout": float("nan")}, "timeout"),
            ({"timeout": float("inf")}, "timeout"),
            ({"timeout": 2**31 / 1000}, "2147483.647"),
            ({"timeout": True}, "timeout"),
            ({"timeout": "60"}, "timeout"),
            ({"max_retries": -1}, "max_retries"),
            ({"max_retries": 1.5}, "max_retries"),
            ({"max_retries": True}, "max_retries"),
            ({"base_url": "ftp://api.flashpi.com.ec"}, "base_url"),
            ({"base_url": "api.flashpi.com.ec"}, "base_url"),
            ({"default_headers": {"IDEMPOTENCY-KEY": "always-the-same"}}, "Idempotency-Key"),
        ],
    )
    def test_validates_its_settings(
        self,
        client_class: type[Flashpi | AsyncFlashpi],
        options: dict[str, object],
        message: str,
    ) -> None:
        with pytest.raises(FlashpiError, match=re.escape(message)):
            client_class(TEST_KEY, **options)  # pyright: ignore[reportArgumentType]

    def test_accepts_the_longest_timeout_and_explicit_none_as_the_defaults(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        assert client_class(TEST_KEY, timeout=2_147_483.647).environment == "test"
        client = client_class(
            TEST_KEY, timeout=None, max_retries=None, language=None, base_url=None
        )
        assert DEFAULT_BASE_URL in repr(client)

    def test_never_shows_the_key(self, client_class: type[Flashpi | AsyncFlashpi]) -> None:
        client = client_class(TEST_KEY)
        assert TEST_KEY not in repr(client)
        assert TEST_KEY not in str(client)
        assert TEST_KEY not in repr(client._engine)  # pyright: ignore[reportPrivateUsage]
        assert TEST_KEY not in repr(client._engine.config)  # pyright: ignore[reportPrivateUsage]
        assert repr(client) == (
            f"{client_class.__name__}(environment='test', base_url='https://api.flashpi.com.ec')"
        )

    def test_refuses_an_http_client_of_the_other_kind(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        other = httpx.AsyncClient() if client_class is Flashpi else httpx.Client()
        with pytest.raises(TypeError, match="http_client"):
            client_class(TEST_KEY, http_client=other)  # pyright: ignore[reportArgumentType]


def test_closes_its_own_http_client_but_not_yours() -> None:
    with Flashpi(TEST_KEY) as flashpi:
        own = flashpi._http_client  # pyright: ignore[reportPrivateUsage]
    assert own.is_closed
    yours = httpx.Client()
    with Flashpi(TEST_KEY, http_client=yours):
        pass
    assert not yours.is_closed
    yours.close()


async def test_closes_its_own_async_http_client_but_not_yours() -> None:
    async with AsyncFlashpi(TEST_KEY) as flashpi:
        own = flashpi._http_client  # pyright: ignore[reportPrivateUsage]
    assert own.is_closed
    yours = httpx.AsyncClient()
    async with AsyncFlashpi(TEST_KEY, http_client=yours):
        pass
    assert not yours.is_closed
    await yours.aclose()


def test_does_not_follow_redirects_of_its_own_http_client() -> None:
    assert not Flashpi(TEST_KEY)._http_client.follow_redirects  # pyright: ignore[reportPrivateUsage]
    assert not AsyncFlashpi(TEST_KEY)._http_client.follow_redirects  # pyright: ignore[reportPrivateUsage]


class TestRequests:
    async def test_sends_the_key_json_headers_and_the_sdk_version(self, make: MakeApi) -> None:
        api = make(json_response({"id": ID}))
        assert await api.call("get", ID) == {"id": ID}
        request = api.sent[0]
        assert str(request.url) == f"https://api.flashpi.com.ec/v1/things/{ID}"
        assert request.method == "GET"
        assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
        assert request.headers["accept"] == "application/json"
        assert request.headers["user-agent"] == f"flashpi-python/{VERSION}"
        assert "accept-language" not in request.headers
        assert "idempotency-key" not in request.headers
        assert "content-type" not in request.headers
        assert request.content == b""

    async def test_trims_spaces_around_a_pasted_key(self, make: MakeApi) -> None:
        api = make(json_response({}), api_key=f"  {TEST_KEY}\n")
        await api.call("status")
        assert api.sent[0].headers["authorization"] == f"Bearer {TEST_KEY}"

    async def test_sends_a_json_body_with_an_idempotency_key_on_post(self, make: MakeApi) -> None:
        api = make(json_response({"id": ID}, 201))
        await api.call("create", {"ruc": "0993411372001", "name": "Panadería Ñandú"})
        request = api.sent[0]
        assert request.method == "POST"
        assert request.headers["content-type"] == "application/json"
        assert UUID.fullmatch(request.headers["idempotency-key"])
        assert request.content == '{"ruc":"0993411372001","name":"Panadería Ñandú"}'.encode()

    async def test_sends_no_body_when_there_is_none(self, make: MakeApi) -> None:
        api = make(json_response({}, 202))
        await api.call("create", None)
        assert api.sent[0].content == b""
        assert "content-type" not in api.sent[0].headers
        assert "idempotency-key" in api.sent[0].headers

    async def test_uses_a_fresh_key_per_call_and_the_callers_key_when_given(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}, 201), json_response({}, 201), json_response({}, 201))
        await api.call("create", {})
        await api.call("create", {})
        await api.call("create", {}, idempotency_key="order-42")
        keys = [request.headers["idempotency-key"] for request in api.sent]
        assert keys[0] != keys[1]
        assert keys[2] == "order-42"

    async def test_never_sends_an_idempotency_key_on_patch_delete_or_get(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}), httpx.Response(204), json_response({}))
        await api.call("update", ID, {}, idempotency_key="ignored")
        await api.call("delete", ID, idempotency_key="ignored")
        await api.call("get", ID, idempotency_key="ignored")
        assert ["idempotency-key" in request.headers for request in api.sent] == [False] * 3
        assert [request.method for request in api.sent] == ["PATCH", "DELETE", "GET"]

    async def test_asks_for_the_client_language_and_lets_a_request_override_it(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}), json_response({}), language="es")
        await api.call("status")
        await api.call("status", language="en")
        assert [request.headers["accept-language"] for request in api.sent] == ["es", "en"]

    async def test_sends_the_correlation_id_and_custom_headers_but_never_replaces_the_key(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}), default_headers={"x-team": "billing"})
        await api.call(
            "status",
            correlation_id="order-42",
            extra_headers={"x-extra": "yes", "Authorization": "Bearer other"},
        )
        headers = api.sent[0].headers
        assert headers["x-correlation-id"] == "order-42"
        assert headers["x-team"] == "billing"
        assert headers["x-extra"] == "yes"
        assert headers.get_list("authorization") == [f"Bearer {TEST_KEY}"]

    async def test_keeps_a_base_url_path_and_drops_its_trailing_slash(self, make: MakeApi) -> None:
        api = make(json_response({}), base_url="http://localhost:3000/proxy/")
        await api.call("status")
        assert str(api.sent[0].url) == "http://localhost:3000/proxy/v1/status"

    async def test_returns_the_response_and_request_id_with_with_response(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({"id": ID}, 200, {"x-request-id": "req_abc"}))
        result = await api.call_with_response("get", ID)
        assert isinstance(result, APIResponse)
        assert result.data == {"id": ID}
        assert result.response.status_code == 200
        assert result.request_id == "req_abc"

    async def test_reads_text_and_bytes_answers(self, make: MakeApi) -> None:
        xml = '<?xml version="1.0" encoding="UTF-8"?><factura>Ñandú</factura>'
        pdf = b"%PDF-1.7\n\xff\xfe binary"
        api = make(
            httpx.Response(200, content=xml.encode(), headers={"content-type": "application/xml"}),
            httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"}),
        )
        assert await api.call("text", ID) == xml
        assert await api.call("raw", ID) == pdf
        assert api.sent[0].headers["accept"] == "application/xml, application/problem+json"
        assert api.sent[1].headers["accept"] == "application/pdf, application/problem+json"

    async def test_returns_none_for_an_empty_or_no_content_answer(self, make: MakeApi) -> None:
        api = make(httpx.Response(204), httpx.Response(200), httpx.Response(202))
        assert await api.call("delete", ID) is None
        assert await api.call("get", ID) is None
        assert await api.call("create", {}) is None

    async def test_sends_a_multipart_body_built_again_for_every_attempt(
        self, make: MakeApi
    ) -> None:
        api = make(httpx.ConnectError("reset"), json_response({"id": ID}, 202))
        content = bytes(range(256))
        await api.call("upload", content, "secret ñ", extra_headers={"content-type": "text/plain"})
        assert len(api.sent) == 2
        for request in api.sent:
            assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
            body = request.content
            assert b'name="password"\r\n\r\nsecret \xc3\xb1\r\n' in body
            assert b'name="file"; filename="certificate.p12"' in body
            assert b"Content-Type: application/x-pkcs12\r\n\r\n" + content in body
        keys = {request.headers["idempotency-key"] for request in api.sent}
        assert len(keys) == 1

    async def test_rejects_empty_path_ids_before_sending_anything(self, make: MakeApi) -> None:
        api = make()
        for value in ("", "  ", None):
            with pytest.raises(FlashpiError, match=r"Missing id in /v1/things/\{id\}"):
                await api.call("get", value)
        with pytest.raises(FlashpiError, match=r"Missing id in /v1/things/\{id\}/parts/\{id\}"):
            await api.call("get_nested", ID, "")
        assert api.sent == []

    async def test_encodes_path_ids(self, make: MakeApi) -> None:
        api = make(json_response({}), json_response({}))
        await api.call("get", "a/b?c#d e")
        await api.call("get", "ñ!~*'()")
        assert api.sent[0].url.raw_path == b"/v1/things/a%2Fb%3Fc%23d%20e"
        assert api.sent[1].url.raw_path == b"/v1/things/%C3%B1!~*'()"

    async def test_raises_a_flashpi_error_when_a_success_body_is_not_json(
        self, make: MakeApi
    ) -> None:
        api = make(httpx.Response(200, content=b"<html>"))
        with pytest.raises(FlashpiError, match="not JSON"):
            await api.call("status")
        assert len(api.sent) == 1

    async def test_refuses_unknown_request_options(self, make: MakeApi) -> None:
        api = make()
        with pytest.raises(TypeError, match="Unknown request options: idempotencykey"):
            await api.call("create", {}, idempotencykey="typo")
        assert api.sent == []

    async def test_refuses_a_body_that_is_not_json(self, make: MakeApi) -> None:
        api = make()
        with pytest.raises(ValueError, match="not JSON compliant"):
            await api.call("create", {"amount": float("nan")})
        assert api.sent == []
