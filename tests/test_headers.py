"""The values that become headers (options, extra and default headers, the language) are checked
before anything is sent, as the Node SDK's `Headers` does: the spaces around a value are trimmed,
and a line break, another control character or a bad name fails at once instead of reaching h11,
which would refuse it on every attempt, retried as a network failure."""

from traceback import format_exception
from typing import Any

import httpx
import pytest

from flashpi import APIConnectionError, AsyncFlashpi, BadRequestError, Flashpi, FlashpiError
from tests.conftest import MakeApi
from tests.support import TEST_KEY, Clock, json_response, problem

pytestmark = pytest.mark.anyio

CLIENTS = [Flashpi, AsyncFlashpi]
BAD_VALUES = ["a\r\nX-Injected: 1", "a\nb", "a\rb", "a\x00b", "a\x0bb", "a\x0cb", "a\x7fb"]
BAD_NAMES = ["x tenant", "x:t", "", "x\r\ny", "x-ñ", "(x)"]


class TestTrimming:
    async def test_trims_the_spaces_around_the_values_of_every_option(self, make: MakeApi) -> None:
        api = make(json_response({}, 201), default_headers={"x-env": " prod\t"}, language=" es ")
        await api.call(
            "create",
            {},
            idempotency_key=" order-42 ",
            correlation_id="\torder-42\r\n",
            extra_headers={"x-tenant": " acme ", "x-tab": "v\t"},
        )
        headers = api.sent[0].headers
        assert headers["idempotency-key"] == "order-42"
        assert headers["x-correlation-id"] == "order-42"
        assert headers["x-tenant"] == "acme"
        assert headers["x-tab"] == "v"
        assert headers["x-env"] == "prod"
        assert headers["accept-language"] == "es"

    async def test_keeps_tabs_spaces_and_non_ascii_text_inside_a_value(self, make: MakeApi) -> None:
        api = make(json_response({}))
        await api.call("status", extra_headers={"x-note": "a b\tc", "x-name": "Ñandú"})
        raw = dict(api.sent[0].headers.raw)
        assert raw[b"x-note"] == b"a b\tc"
        assert raw[b"x-name"] == "Ñandú".encode()

    async def test_sends_text_outside_ascii_as_utf8_on_a_post_and_in_default_headers(
        self, make: MakeApi
    ) -> None:
        api = make(json_response({}, 201), default_headers={"x-env": "Peñafiel"})
        await api.call("create", {}, extra_headers={"x-name": "Ñandú"})
        raw = dict(api.sent[0].headers.raw)
        assert raw[b"x-name"] == "Ñandú".encode()
        assert raw[b"x-env"] == "Peñafiel".encode()

    async def test_takes_the_last_spelling_of_a_repeated_idempotency_key_header(
        self, make: MakeApi
    ) -> None:
        api = make(problem(400, "validation_failed"))
        repeated = {"Idempotency-Key": "order-1", "idempotency-key": "order-2"}
        with pytest.raises(BadRequestError) as caught:
            await api.call("create", {}, extra_headers=repeated)
        assert api.sent[0].headers.get_list("idempotency-key") == ["order-2"]
        assert caught.value.idempotency_key == "order-2"

    async def test_puts_the_trimmed_idempotency_key_on_errors(self, make: MakeApi) -> None:
        api = make(problem(400, "validation_failed"))
        with pytest.raises(BadRequestError) as caught:
            await api.call("create", {}, idempotency_key=" order-42 ")
        assert caught.value.idempotency_key == "order-42"
        assert api.sent[0].headers["idempotency-key"] == "order-42"

    async def test_takes_the_trimmed_idempotency_key_header_as_the_key(self, make: MakeApi) -> None:
        api = make(json_response({}, 201))
        await api.call("create", {}, extra_headers={"Idempotency-Key": " order-7 "})
        assert api.sent[0].headers.get_list("idempotency-key") == ["order-7"]


class TestRefusingBeforeSending:
    @pytest.mark.parametrize("value", BAD_VALUES)
    async def test_refuses_a_control_character_in_any_value_without_retrying(
        self, make: MakeApi, clock: Clock, value: str
    ) -> None:
        api = make()
        calls: list[dict[str, Any]] = [
            {"idempotency_key": value},
            {"correlation_id": value},
            {"language": value},
            {"extra_headers": {"x-tenant": value}},
        ]
        for options in calls:
            with pytest.raises(ValueError, match="line break or another control") as caught:
                await api.call("create", {}, **options)
            assert not isinstance(caught.value, FlashpiError)
            assert "X-Injected" not in str(caught.value)
        assert api.sent == []
        assert clock.sleeps == []

    async def test_refuses_a_lone_surrogate_in_any_value_without_showing_it(
        self, make: MakeApi
    ) -> None:
        api = make()
        value = "tok\ud800en-SECRET"
        calls: list[dict[str, Any]] = [
            {"idempotency_key": value},
            {"correlation_id": value},
            {"language": value},
            {"extra_headers": {"x-tenant": value}},
        ]
        for options in calls:
            with pytest.raises(ValueError, match="cannot be sent as UTF-8") as caught:
                await api.call("create", {}, **options)
            assert "SECRET" not in str(caught.value)
            assert "SECRET" not in repr(caught.value)
        assert api.sent == []

    @pytest.mark.parametrize("name", BAD_NAMES)
    async def test_refuses_a_bad_header_name(self, make: MakeApi, name: str) -> None:
        api = make()
        with pytest.raises(ValueError, match="is not a valid header name"):
            await api.call("status", extra_headers={name: "v"})
        assert api.sent == []

    @pytest.mark.parametrize("option", ["idempotency_key", "correlation_id", "language"])
    async def test_refuses_an_option_that_is_not_text(self, make: MakeApi, option: str) -> None:
        api = make()
        with pytest.raises(TypeError, match=f"{option} must be str, not int"):
            await api.call("create", {}, **{option: 123})
        assert api.sent == []

    async def test_refuses_extra_headers_that_are_not_a_mapping_or_names_that_are_not_text(
        self, make: MakeApi
    ) -> None:
        api = make()
        with pytest.raises(TypeError, match="extra_headers must be a mapping"):
            await api.call("status", extra_headers=[("x-a", "b")])
        with pytest.raises(TypeError, match="Header names must be str, not bytes"):
            await api.call("status", extra_headers={b"x-a": "b"})
        assert api.sent == []


@pytest.mark.parametrize("client_class", CLIENTS)
class TestTheClientSettings:
    @pytest.mark.parametrize("value", BAD_VALUES)
    def test_refuses_a_control_character_in_default_headers_or_the_language(
        self, client_class: type[Flashpi | AsyncFlashpi], value: str
    ) -> None:
        with pytest.raises(ValueError, match="'x-env' has a line break"):
            client_class(TEST_KEY, default_headers={"x-env": value})
        with pytest.raises(ValueError, match="language has a line break"):
            client_class(TEST_KEY, language=value)  # pyright: ignore[reportArgumentType]

    def test_refuses_a_lone_surrogate_in_default_headers_without_showing_it(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        with pytest.raises(ValueError, match="'x-env' has a character that cannot") as caught:
            client_class(TEST_KEY, default_headers={"x-env": "tok\ud800en-SECRET"})
        assert "SECRET" not in str(caught.value)

    @pytest.mark.parametrize("name", BAD_NAMES)
    def test_refuses_a_bad_default_header_name(
        self, client_class: type[Flashpi | AsyncFlashpi], name: str
    ) -> None:
        with pytest.raises(ValueError, match="is not a valid header name"):
            client_class(TEST_KEY, default_headers={name: "v"})

    def test_refuses_a_language_or_default_headers_of_the_wrong_type(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        with pytest.raises(TypeError, match="language must be str, not int"):
            client_class(TEST_KEY, language=1)  # pyright: ignore[reportArgumentType]
        with pytest.raises(TypeError, match="default_headers must be a mapping"):
            client_class(TEST_KEY, default_headers=[("x-a", "b")])  # pyright: ignore[reportArgumentType]

    def test_refuses_an_idempotency_key_in_default_headers_even_with_spaces(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        with pytest.raises(FlashpiError, match="Idempotency-Key"):
            client_class(TEST_KEY, default_headers={"Idempotency-Key": " k "})


class TestARequestHttpxRefuses:
    """What still reaches h11 and is refused there (LocalProtocolError) is not retried, and its
    message, which quotes the refused header, is left out: it may be the Authorization header."""

    async def test_is_a_flashpi_error_without_httpxs_reason(
        self, make: MakeApi, clock: Clock
    ) -> None:
        refused = httpx.LocalProtocolError(f"Illegal header value b'Bearer {TEST_KEY}'")
        api = make(refused, json_response({}))
        with pytest.raises(FlashpiError, match="was not sent: httpx refused it") as caught:
            await api.call("create", {}, idempotency_key="order-1")
        error = caught.value
        assert not isinstance(error, APIConnectionError)
        assert error.idempotency_key == "order-1"
        shown = [str(error), repr(error), *format_exception(error)]
        assert not any(TEST_KEY in text for text in shown)
        assert error.__cause__ is None
        assert error.__suppress_context__
        assert len(api.sent) == 1
        assert clock.sleeps == []
