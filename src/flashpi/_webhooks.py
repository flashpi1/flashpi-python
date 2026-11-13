"""Verification of the webhooks Flashpi sends (Standard Webhooks).

A webhook is signed with HMAC-SHA256 over `webhook-id.webhook-timestamp.body` using the endpoint's
`whsec_` secret. During a secret rotation Flashpi signs with both secrets, so the
`webhook-signature` header lists several signatures.
"""

import base64
import hashlib
import hmac
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import TypeAlias, cast

from ._errors import WebhookVerificationError
from .types import WebhookEvent

WebhookHeaders: TypeAlias = Mapping[str, str | Sequence[str] | None]
"""The request headers of a webhook: any mapping (Django's `request.headers`, Starlette's,
httpx's, a dict). Names are matched without case; repeated headers may come as lists."""

WebhookPayload: TypeAlias = str | bytes | bytearray | memoryview
"""The exact body of the webhook request, before any JSON parsing."""

WEBHOOK_TOLERANCE_SECONDS = 300
"""Default largest gap, in seconds, between a webhook's timestamp and the receiver's clock."""

_SECRET_PREFIX = "whsec_"  # noqa: S105 (a prefix, not a secret)
# Key sizes of a Standard Webhooks secret (Flashpi makes 32-byte keys).
_MIN_SECRET_BYTES = 24
_MAX_SECRET_BYTES = 64
_SIGNATURE_BYTES = 32
_TIMESTAMP = re.compile(r"[0-9]{1,12}")
_BASE64 = re.compile(r"[A-Za-z0-9+/]*={0,2}")


def verify_webhook_signature(
    payload: WebhookPayload,
    headers: WebhookHeaders,
    secret: str,
    *,
    tolerance: float | None = None,
    now: datetime | float | None = None,
) -> None:
    """Checks that a webhook comes from Flashpi and is recent.

    Raises a WebhookVerificationError otherwise: answer 400 and ignore the request. Pass the raw
    body exactly as received; a body parsed and serialized again does not match.

    Args:
        payload: The raw body (str or bytes).
        headers: The request headers.
        secret: The endpoint's signing secret (`whsec_...`).
        tolerance: Largest gap, in seconds, between `webhook-timestamp` and now (default 300).
        now: The current time, for tests: a datetime or Unix seconds (default: the clock).
    """
    tolerance_seconds, now_seconds = _verify_options(tolerance, now)
    # Error trackers record the local variables of the frames an error passes through, so none
    # of the frames that raise keeps the decoded key or the expected signature.
    signer = _signer(secret)
    webhook_id = _header(headers, "webhook-id")
    timestamp = _header(headers, "webhook-timestamp")
    signatures = _header(headers, "webhook-signature")
    if not webhook_id or not timestamp or not signatures:
        raise WebhookVerificationError(
            "missing_headers",
            "The webhook-id, webhook-timestamp and webhook-signature headers are required",
        )
    if not _TIMESTAMP.fullmatch(timestamp):
        raise WebhookVerificationError("invalid_timestamp", "The webhook-timestamp is not valid")
    # Written so that anything unexpected fails closed.
    if not abs(math.floor(now_seconds) - int(timestamp)) <= tolerance_seconds:
        raise WebhookVerificationError(
            "timestamp_out_of_range",
            f"The webhook-timestamp is more than {tolerance_seconds:g} seconds away from now",
        )

    try:
        prefix = f"{webhook_id}.{timestamp}.".encode()
    except UnicodeEncodeError:
        # A webhook-id that is not text (a framework's surrogate escape of non-UTF-8 bytes) was
        # not signed by Flashpi; Node's TextEncoder ends at the same reason.
        raise WebhookVerificationError(
            "no_matching_signature", "No webhook-signature matches the body and the secret"
        ) from None
    if _signed(signer, prefix + _payload_bytes(payload), signatures):
        return
    raise WebhookVerificationError(
        "no_matching_signature", "No webhook-signature matches the body and the secret"
    )


def unwrap_webhook(
    payload: WebhookPayload,
    headers: WebhookHeaders,
    secret: str,
    *,
    tolerance: float | None = None,
    now: datetime | float | None = None,
) -> WebhookEvent:
    """Verifies a webhook (see `verify_webhook_signature`) and returns its parsed body.

    Narrow the event on `event["type"]`. Endpoints in thin mode receive no `data`:
    `cast(ThinWebhookEvent, unwrap_webhook(...))`.

    ```python
    event = unwrap_webhook(raw_body, request.headers, os.environ["FLASHPI_WEBHOOK_SECRET"])
    if event["type"] == "webhook_endpoint.verification":
        return {"challenge": event["data"]["challenge"]}
    ```
    """
    verify_webhook_signature(payload, headers, secret, tolerance=tolerance, now=now)
    text = payload if isinstance(payload, str) else bytes(payload).decode("utf-8", errors="replace")
    try:
        event: object = json.loads(text)
    except (ValueError, RecursionError) as error:
        raise WebhookVerificationError("invalid_payload", "The webhook body is not JSON") from error
    if not isinstance(event, dict):
        raise WebhookVerificationError("invalid_payload", "The webhook body is not a JSON object")
    return cast("WebhookEvent", event)


class Webhooks:
    """Webhook helpers, also available as `client.webhooks`. They need no API key."""

    def verify_signature(
        self,
        payload: WebhookPayload,
        headers: WebhookHeaders,
        secret: str,
        *,
        tolerance: float | None = None,
        now: datetime | float | None = None,
    ) -> None:
        """See `verify_webhook_signature`."""
        verify_webhook_signature(payload, headers, secret, tolerance=tolerance, now=now)

    def unwrap(
        self,
        payload: WebhookPayload,
        headers: WebhookHeaders,
        secret: str,
        *,
        tolerance: float | None = None,
        now: datetime | float | None = None,
    ) -> WebhookEvent:
        """See `unwrap_webhook`."""
        return unwrap_webhook(payload, headers, secret, tolerance=tolerance, now=now)


def _header(headers: WebhookHeaders, name: str) -> str | None:
    """A header without case. Repeated headers: signature lists are joined, otherwise the first."""
    values: list[str] = []
    for key, value in headers.items():
        if key.lower() != name or value is None:
            continue
        if isinstance(value, str):
            values.append(value)
        else:
            values.extend(item for item in value if isinstance(cast("object", item), str))
    if not values:
        return None
    return " ".join(values) if name == "webhook-signature" else values[0]


def _signed(signer: hmac.HMAC, message: bytes, signatures: str) -> bool:
    """Whether a v1 signature of the header signs `message`. It returns instead of raising, so
    the expected signature never stays in the frame of an error."""
    # One HMAC per request, however many signatures the header lists.
    signer.update(message)
    expected = signer.digest()
    for entry in signatures.split(" "):
        version, comma, encoded = entry.partition(",")
        if not comma or version != "v1":
            continue
        signature = _decode_base64(encoded)
        if (
            signature is not None
            and len(signature) == _SIGNATURE_BYTES
            and hmac.compare_digest(signature, expected)
        ):
            return True
    return False


def _signer(secret: object) -> hmac.HMAC:
    """An HMAC-SHA256 keyed with the decoded secret. When the secret is refused, the decoded key
    is dropped before raising: an incomplete key is still most of the secret."""
    if not isinstance(secret, str) or secret.strip() == "":
        raise WebhookVerificationError(
            "invalid_secret",
            "The webhook secret is empty: copy it from the console or "
            "webhook_endpoints.get_secret()",
        )
    key = _decode_base64(secret.strip().removeprefix(_SECRET_PREFIX))
    size = len(key) if key else 0
    if key and _MIN_SECRET_BYTES <= size <= _MAX_SECRET_BYTES:
        return hmac.new(key, digestmod=hashlib.sha256)
    del key
    if size == 0:
        raise WebhookVerificationError(
            "invalid_secret", "The webhook secret is not a whsec_ secret (base64 after the prefix)"
        )
    raise WebhookVerificationError(
        "invalid_secret",
        "The webhook secret is not a complete whsec_ secret: copy it again from the console "
        "or webhook_endpoints.get_secret()",
    )


def _verify_options(tolerance: object, now: object) -> tuple[float, float]:
    """The checked tolerance and clock. Bad values are programming errors: TypeError or
    ValueError, never a skipped time check."""
    value = WEBHOOK_TOLERANCE_SECONDS if tolerance is None else tolerance
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("tolerance must be a number of seconds, 0 or more")
    if not math.isfinite(value) or value < 0:
        raise ValueError("tolerance must be a number of seconds, 0 or more")
    if now is None:
        seconds = time.time()
    elif isinstance(now, datetime):
        seconds = now.timestamp()
    elif isinstance(now, bool) or not isinstance(now, int | float):
        raise TypeError("now must be a datetime or a number of Unix seconds")
    else:
        try:
            seconds = float(now)
        except OverflowError as error:
            raise ValueError("now must be a datetime or a number of Unix seconds") from error
    if not math.isfinite(seconds):
        raise ValueError("now must be a datetime or a number of Unix seconds")
    return float(value), seconds


def _payload_bytes(payload: object) -> bytes:
    if isinstance(payload, str):
        try:
            return payload.encode()
        except UnicodeEncodeError as error:
            raise WebhookVerificationError(
                "invalid_payload", "The webhook body is not valid text"
            ) from error
    if isinstance(payload, bytes | bytearray | memoryview):
        return bytes(cast("bytes", payload))
    raise WebhookVerificationError(
        "invalid_payload",
        "Pass the raw webhook body as str or bytes (not parsed JSON)",
    )


def _decode_base64(value: str) -> bytes | None:
    """Standard base64 to bytes, or None when it is not base64 (padding optional, like atob)."""
    if not _BASE64.fullmatch(value) or len(value) % 4 == 1:
        return None
    data = value.rstrip("=") if len(value) % 4 == 0 else value
    if "=" in data or len(data) % 4 == 1:
        return None
    # Only the alphabet is left, in a length that decodes once padded.
    return base64.b64decode(data + "=" * (-len(data) % 4), validate=True)
