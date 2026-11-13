"""Webhook verification (Node: test/webhooks.test.ts and the webhook part of
test/review-fixes.test.ts), with the vectors of Standard Webhooks and of Flashpi's docs."""

import base64
import hashlib
import hmac
import json
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, NamedTuple, assert_type, cast

import httpx
import pytest

import flashpi
from flashpi import (
    WEBHOOK_TOLERANCE_SECONDS,
    AsyncFlashpi,
    Flashpi,
    WebhookHeaders,
    WebhookVerificationError,
    unwrap_webhook,
    verify_webhook_signature,
)
from flashpi.types import ThinWebhookEvent, WebhookEvent
from tests.support import TEST_KEY


class Vector(NamedTuple):
    secret: str
    id: str
    timestamp: str
    body: str
    signature: str


# The example of the Standard Webhooks specification (24-byte key).
STANDARD = Vector(
    secret="whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw",  # noqa: S106 (a published test vector)
    id="msg_p5jXN8AQM9LWM0D4loKWxJek",
    timestamp="1614265330",
    body='{"test": 2432232314}',
    signature="v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE=",
)

# The example of Flashpi's webhook docs (32-byte key), the same the API's tests sign.
FLASHPI = Vector(
    secret="whsec_Zmxhc2hwaS1kb2NzLWV4YW1wbGUtc2VjcmV0LTMyLWI=",  # noqa: S106 (published)
    id="019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6a7b",
    timestamp="1792152000",
    body=(
        '{"id":"019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6a7b","type":"invoice.authorized",'
        '"environment":"test","createdAt":"2026-10-16T17:20:00.000Z"}'
    ),
    signature="v1,HbWOpDPWCo3wtq41t9GVHUpg69M1zgvveoDJmSWkA8U=",
)

DECOY = "v1,Ceo5qEr07ixe2NLpvHk3FH9bwy/WavXrAFQ/9tdO6mc="


def headers_of(vector: Vector, signature: str | None = None) -> dict[str, str]:
    return {
        "webhook-id": vector.id,
        "webhook-timestamp": vector.timestamp,
        "webhook-signature": vector.signature if signature is None else signature,
    }


def at(vector: Vector, offset: int = 0) -> int:
    """`now` for a vector: its timestamp, plus `offset` seconds."""
    return int(vector.timestamp) + offset


def reason(check: Callable[[], object]) -> str:
    try:
        check()
    except WebhookVerificationError as error:
        return error.reason
    return "verified"


def sign(key: bytes, vector: Vector, body: bytes) -> str:
    signed = f"{vector.id}.{vector.timestamp}.".encode() + body
    return "v1," + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


class TestVerifyWebhookSignature:
    def test_accepts_the_standard_webhooks_example(self) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            STANDARD.body, headers_of(STANDARD), STANDARD.secret, now=at(STANDARD)
        )
        assert reason(check) == "verified"

    def test_accepts_the_example_of_flashpis_docs(self) -> None:
        verify_webhook_signature(FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI))

    def test_signs_the_raw_bytes_a_utf8_body_as_text_or_bytes(self) -> None:
        body = (
            '{"id":"019a1b2c-3d4e-7f60-8a1b-2c3d4e5f6a7b","type":"invoice.authorized",'
            '"environment":"test","createdAt":"2026-10-16T17:20:00.000Z",'
            '"data":{"counterparty":{"name":"Panadería Ñandú €"}}}'
        )
        headers = headers_of(FLASHPI, "v1,fdAGYFcvd+G8WvVy6jtQtuduKm8mENxuA/zTqcWYSJY=")
        encoded = body.encode()
        assert len(encoded) == 191
        for payload in (body, encoded, bytearray(encoded), memoryview(encoded)):
            verify_webhook_signature(payload, headers, FLASHPI.secret, now=at(FLASHPI))

    def test_accepts_a_body_of_any_bytes(self) -> None:
        headers = headers_of(STANDARD, "v1,sEcZ042G8Crqgxbybb3y0eDxQR3TcfYsk11I1XULhSI=")
        verify_webhook_signature(bytes(range(256)), headers, STANDARD.secret, now=at(STANDARD))

    def test_accepts_either_secret_during_a_rotation(self) -> None:
        rotation = f"{FLASHPI.signature} v1,dZdgetSIp5ZOSjhz50Gcz1N1hb/WBvK3IdncOP52NrQ="
        for secret in (FLASHPI.secret, STANDARD.secret):
            headers = headers_of(FLASHPI, rotation)
            verify_webhook_signature(FLASHPI.body, headers, secret, now=at(FLASHPI))

    def test_skips_decoys_malformed_entries_and_other_versions(self) -> None:
        signature = " ".join(
            [DECOY, "v2," + FLASHPI.signature[3:], "v1", "v1,not-base64!", "", FLASHPI.signature]
        )
        headers = headers_of(FLASHPI, signature)
        verify_webhook_signature(FLASHPI.body, headers, FLASHPI.secret, now=at(FLASHPI))

    def test_accepts_the_secret_without_its_prefix_and_with_spaces_around_it(self) -> None:
        secret = f" {FLASHPI.secret.removeprefix('whsec_')}\n"
        verify_webhook_signature(FLASHPI.body, headers_of(FLASHPI), secret, now=at(FLASHPI))

    @pytest.mark.parametrize(
        ("body", "signature"),
        [
            (FLASHPI.body.replace("test", "live"), FLASHPI.signature),
            (FLASHPI.body, "v2," + FLASHPI.signature[3:]),
            (FLASHPI.body, FLASHPI.signature[:-4]),
            (FLASHPI.body, "v1,"),
            (FLASHPI.body, "v1,dawfeoifkpqwoekfpqoekf"),
        ],
        ids=["altered body", "other version", "truncated", "empty", "garbage"],
    )
    def test_rejects_bad_signatures(self, body: str, signature: str) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            body, headers_of(FLASHPI, signature), FLASHPI.secret, now=at(FLASHPI)
        )
        assert reason(check) == "no_matching_signature"

    def test_accepts_a_signature_without_its_padding_like_atob(self) -> None:
        headers = headers_of(FLASHPI, FLASHPI.signature.rstrip("="))
        verify_webhook_signature(FLASHPI.body, headers, FLASHPI.secret, now=at(FLASHPI))

    def test_rejects_a_body_signed_with_another_secret(self) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers_of(FLASHPI), STANDARD.secret, now=at(FLASHPI)
        )
        assert reason(check) == "no_matching_signature"

    def test_accepts_timestamps_up_to_5_minutes_away_and_rejects_others(self) -> None:
        def check(offset: int) -> str:
            return reason(
                lambda: verify_webhook_signature(
                    FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI, offset)
                )
            )

        assert WEBHOOK_TOLERANCE_SECONDS == 300
        assert [check(300), check(-300), check(301), check(-301)] == [
            "verified",
            "verified",
            "timestamp_out_of_range",
            "timestamp_out_of_range",
        ]

    def test_takes_another_tolerance_and_a_datetime_as_now(self) -> None:
        now = datetime.fromtimestamp(at(FLASHPI, 11), UTC)
        with pytest.raises(WebhookVerificationError, match="more than 10 seconds") as caught:
            verify_webhook_signature(
                FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, tolerance=10, now=now
            )
        assert caught.value.reason == "timestamp_out_of_range"
        later = datetime.fromtimestamp(at(FLASHPI, 10), UTC)
        verify_webhook_signature(
            FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, tolerance=10.5, now=later
        )

    def test_checks_the_timestamp_against_the_current_clock_by_default(self) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret
        )
        assert reason(check) == "timestamp_out_of_range"

    @pytest.mark.parametrize("name", ["webhook-id", "webhook-timestamp", "webhook-signature"])
    def test_rejects_a_request_without_a_header(self, name: str) -> None:
        headers = {key: value for key, value in headers_of(FLASHPI).items() if key != name}
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers, FLASHPI.secret, now=at(FLASHPI)
        )
        assert reason(check) == "missing_headers"

    @pytest.mark.parametrize("timestamp", ["abc", "-1", "1792152000.5", "1234567890123", "١٧٩"])
    def test_rejects_an_invalid_timestamp(self, timestamp: str) -> None:
        headers = {**headers_of(FLASHPI), "webhook-timestamp": timestamp}
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers, FLASHPI.secret, now=at(FLASHPI)
        )
        assert reason(check) == "invalid_timestamp"

    @pytest.mark.parametrize(
        "secret", ["", "whsec_", "   ", "whsec_not base64!", "whsec_a", "whsec_ab="]
    )
    def test_refuses_an_invalid_secret(self, secret: str) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers_of(FLASHPI), secret, now=at(FLASHPI)
        )
        assert reason(check) == "invalid_secret"

    def test_refuses_a_secret_that_is_not_a_string(self) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body,
            headers_of(FLASHPI),
            cast("str", None),
            now=at(FLASHPI),
        )
        assert reason(check) == "invalid_secret"

    @pytest.mark.parametrize(
        "payload", [json.loads(FLASHPI.body), None, 42], ids=["parsed", "none", "number"]
    )
    def test_refuses_a_body_that_was_already_parsed(self, payload: object) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            cast("str", payload), headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)
        )
        assert reason(check) == "invalid_payload"

    def test_refuses_a_text_body_that_cannot_be_encoded(self) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            "\ud800", headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)
        )
        assert reason(check) == "invalid_payload"

    def test_reads_headers_in_any_letter_case_and_joins_repeated_signatures(self) -> None:
        class MultiHeaders(Mapping[str, str]):
            """Headers whose items repeat a name, like Starlette's."""

            def __init__(self, items: list[tuple[str, str]]) -> None:
                self._items = items

            def __getitem__(self, key: str) -> str:
                return next(value for name, value in self._items if name == key)

            def __iter__(self) -> Iterator[str]:
                return (name for name, _ in self._items)

            def __len__(self) -> int:
                return len(self._items)

            def items(self) -> Any:
                return list(self._items)

        variants: list[WebhookHeaders] = [
            httpx.Headers(headers_of(FLASHPI)),
            {
                "Webhook-Id": FLASHPI.id,
                "WEBHOOK-TIMESTAMP": FLASHPI.timestamp,
                "webhook-signature": FLASHPI.signature,
            },
            {
                "webhook-id": [FLASHPI.id, "ignored"],
                "webhook-timestamp": (FLASHPI.timestamp,),
                "webhook-signature": [DECOY, FLASHPI.signature],
                "other": None,
            },
            MultiHeaders(
                [
                    ("webhook-id", FLASHPI.id),
                    ("webhook-timestamp", FLASHPI.timestamp),
                    ("webhook-signature", DECOY),
                    ("webhook-signature", FLASHPI.signature),
                ]
            ),
        ]
        for headers in variants:
            verify_webhook_signature(FLASHPI.body, headers, FLASHPI.secret, now=at(FLASHPI))


class TestUnwrapWebhook:
    def test_returns_the_verified_event(self) -> None:
        event = unwrap_webhook(FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI))
        assert_type(event, WebhookEvent)
        assert event == json.loads(FLASHPI.body)
        assert event["type"] == "invoice.authorized"

    def test_reads_a_bytes_body(self) -> None:
        event = unwrap_webhook(
            FLASHPI.body.encode(), headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)
        )
        assert event["id"] == FLASHPI.id

    def test_types_a_thin_event_without_data(self) -> None:
        event = cast(
            "ThinWebhookEvent",
            unwrap_webhook(FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)),
        )
        assert event["type"] == "invoice.authorized"
        assert "data" not in event

    def test_raises_before_parsing_when_the_signature_is_wrong(self) -> None:
        check = lambda: unwrap_webhook(  # noqa: E731
            "not json", headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)
        )
        assert reason(check) == "no_matching_signature"

    @pytest.mark.parametrize("body", ["not json", "[1, 2]", '"text"'])
    def test_raises_invalid_payload_for_a_signed_body_that_is_not_a_json_object(
        self, body: str
    ) -> None:
        key = base64.b64decode(STANDARD.secret.removeprefix("whsec_"))
        headers = headers_of(STANDARD, sign(key, STANDARD, body.encode()))
        check = lambda: unwrap_webhook(body, headers, STANDARD.secret, now=at(STANDARD))  # noqa: E731
        assert reason(check) == "invalid_payload"

    @pytest.mark.parametrize("client_class", [Flashpi, AsyncFlashpi])
    def test_is_available_on_the_clients_as_webhooks(
        self, client_class: type[Flashpi | AsyncFlashpi]
    ) -> None:
        client = client_class(TEST_KEY)
        event = client.webhooks.unwrap(
            FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)
        )
        assert event["id"] == FLASHPI.id
        client.webhooks.verify_signature(
            FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, now=at(FLASHPI)
        )


class TestHardening:
    @pytest.mark.parametrize(
        ("options", "error_class"),
        [
            ({"tolerance": float("nan")}, ValueError),
            ({"tolerance": -1}, ValueError),
            ({"tolerance": float("inf")}, ValueError),
            ({"tolerance": "300"}, TypeError),
            ({"tolerance": True}, TypeError),
            ({"now": float("nan")}, ValueError),
            ({"now": float("inf")}, ValueError),
            ({"now": 10**400}, ValueError),
            ({"now": "2026-10-16"}, TypeError),
            ({"now": False}, TypeError),
        ],
    )
    def test_refuses_bad_options_instead_of_skipping_the_time_check(
        self, options: dict[str, Any], error_class: type[Exception]
    ) -> None:
        settings = {"now": at(FLASHPI), **options}
        with pytest.raises(error_class):
            verify_webhook_signature(FLASHPI.body, headers_of(FLASHPI), FLASHPI.secret, **settings)

    def test_computes_the_hmac_once_however_many_signatures_the_header_lists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[bytes] = []
        original = hmac.new

        def counting(key: bytes, message: bytes, digestmod: Any) -> Any:
            calls.append(message)
            return original(key, message, digestmod)

        monkeypatch.setattr(hmac, "new", counting)
        signature = " ".join([DECOY] * 300 + [FLASHPI.signature])
        event = unwrap_webhook(
            FLASHPI.body, headers_of(FLASHPI, signature), FLASHPI.secret, now=at(FLASHPI)
        )
        assert event["type"] == "invoice.authorized"
        assert len(calls) == 1

    @pytest.mark.parametrize(
        "secret",
        ["whsec_Zmxhc2hw", "whsec_test", "whsec_" + base64.b64encode(b"x" * 65).decode()],
        ids=["6-byte key", "placeholder", "65-byte key"],
    )
    def test_reports_incomplete_secrets_as_invalid_secret(self, secret: str) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers_of(FLASHPI), secret, now=at(FLASHPI)
        )
        assert reason(check) == "invalid_secret"

    def test_reports_a_bad_secret_before_a_stale_timestamp(self) -> None:
        check = lambda: verify_webhook_signature(  # noqa: E731
            FLASHPI.body, headers_of(FLASHPI), "whsec_test"
        )
        assert reason(check) == "invalid_secret"

    def test_accepts_a_64_byte_key(self) -> None:
        key = bytes([7] * 64)
        signature = sign(key, FLASHPI, FLASHPI.body.encode())
        secret = "whsec_" + base64.b64encode(key).decode()
        verify_webhook_signature(
            FLASHPI.body, headers_of(FLASHPI, signature), secret, now=at(FLASHPI)
        )

    def test_accepts_an_unpadded_secret(self) -> None:
        verify_webhook_signature(
            FLASHPI.body,
            headers_of(FLASHPI),
            FLASHPI.secret.rstrip("="),
            now=at(FLASHPI),
        )


def test_the_webhook_helpers_are_exported() -> None:
    assert flashpi.Webhooks().unwrap is not None
    assert flashpi.WebhookPayload is not None
