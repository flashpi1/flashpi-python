"""Checks of the numeric settings, shared by the clients and every request."""

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
