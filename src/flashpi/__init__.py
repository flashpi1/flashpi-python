"""The official Python SDK for Flashpi, the electronic invoicing API for Ecuador's SRI."""

from ._client import DEFAULT_BASE_URL, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, AsyncFlashpi, Flashpi
from ._errors import (
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
    WebhookVerificationError,
    WebhookVerificationReason,
)
from ._http import RequestOptions
from ._response import APIResponse
from ._version import VERSION
from .types import ApiErrorCode, ApiFieldErrorCode, FieldError, Language, Problem

__version__ = VERSION

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "VERSION",
    "APIConnectionError",
    "APIError",
    "APIResponse",
    "APITimeoutError",
    "ApiErrorCode",
    "ApiFieldErrorCode",
    "AsyncFlashpi",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "FieldError",
    "Flashpi",
    "FlashpiError",
    "InternalServerError",
    "Language",
    "NotFoundError",
    "PermissionDeniedError",
    "Problem",
    "RateLimitError",
    "RequestOptions",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "WebhookVerificationReason",
    "__version__",
]
