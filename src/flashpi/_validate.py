"""Checks of the settings, shared by the clients and every request."""

import re
from collections.abc import Mapping
from typing import cast

from ._errors import FlashpiError

MAX_TIMEOUT = 2_147_483.647
"""The longest timeout, in seconds: the Node SDK's limit (2147483647 ms), so both SDKs accept the
same values."""

_TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
"""A header name (RFC 9110 `token`)."""
_HTTP_WHITESPACE = " \t\r\n"
"""Trimmed from both ends of a header value, as the Fetch standard's `Headers` does."""
_CONTROL = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
"""What h11 refuses inside a header value: control characters other than the tab."""


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


def header_name(name: object) -> str:
    """A header name: an RFC 9110 token. TypeError when it is not text, ValueError otherwise."""
    if not isinstance(name, str):
        raise TypeError(f"Header names must be str, not {type(name).__name__}")
    if not _TOKEN.fullmatch(name):
        raise ValueError(f"{name!r} is not a valid header name")
    return name


def header_value(label: str, value: object) -> str:
    """A header value without the spaces, tabs and line breaks around it, as the Node SDK's
    `Headers` sends it.

    Checked by the SDK itself before anything is sent, so a bad value is never retried as a
    network failure (h11 refuses it once the request is on its way): TypeError when it is not
    text (httpx 0.27 and 0.28 fail on those differently), ValueError when a line break or another
    control character is left. The message never shows the value, which may be a secret.
    """
    if not isinstance(value, str):
        raise TypeError(f"{label} must be str, not {type(value).__name__}")
    trimmed = value.strip(_HTTP_WHITESPACE)
    if _CONTROL.search(trimmed):
        raise ValueError(f"{label} has a line break or another control character")
    return trimmed


def checked_headers(label: str, headers: object) -> dict[str, str]:
    """The headers of a mapping, each name and value checked (`header_name`, `header_value`)."""
    if headers is None:
        return {}
    if not isinstance(headers, Mapping):
        raise TypeError(f"{label} must be a mapping of header names to values")
    checked: dict[str, str] = {}
    for name, value in cast("Mapping[object, object]", headers).items():
        valid = header_name(name)
        checked[valid] = header_value(f"The value of header {valid!r}", value)
    return checked
