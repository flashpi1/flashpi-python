"""Checks of the settings, shared by the clients and every request."""

from collections.abc import Mapping
from typing import cast

from ._errors import FlashpiError

MAX_TIMEOUT = 2_147_483.647
"""The longest timeout, in seconds: the Node SDK's limit (2147483647 ms), so both SDKs accept the
same values."""


def valid_timeout(name: str, value: object) -> float:
    """A timeout in seconds: more than 0 and at most `MAX_TIMEOUT`."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not 0 < value <= MAX_TIMEOUT
    ):
        raise FlashpiError(f"{name} must be more than 0 and at most {MAX_TIMEOUT} seconds")
    return float(value)


def valid_retries(name: str, value: object) -> int:
    """A number of retries: a whole number, 0 or more."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FlashpiError(f"{name} must be a whole number, 0 or more")
    return value


def check_header_values(headers: object) -> None:
    """Refuses header values that are not text with a TypeError, before httpx sees them: httpx
    0.28 raises one for most values but 0.27 an AttributeError, and bytes fail later on both."""
    if not isinstance(headers, Mapping):
        return
    for value in cast("Mapping[object, object]", headers).values():
        if not isinstance(value, str):
            raise TypeError(f"Header value must be str, not {type(value).__name__}")
