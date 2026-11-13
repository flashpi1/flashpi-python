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
from ._pagination import AsyncPage, AsyncPaginator, Page
from ._response import APIResponse
from ._version import VERSION
from ._webhooks import (
    WEBHOOK_TOLERANCE_SECONDS,
    WebhookHeaders,
    WebhookPayload,
    Webhooks,
    unwrap_webhook,
    verify_webhook_signature,
)
from .types import ApiErrorCode, ApiFieldErrorCode, FieldError, Language, Problem

__version__ = VERSION

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT",
    "VERSION",
    "WEBHOOK_TOLERANCE_SECONDS",
    "APIConnectionError",
    "APIError",
    "APIResponse",
    "APITimeoutError",
    "ApiErrorCode",
    "ApiFieldErrorCode",
    "AsyncFlashpi",
    "AsyncPage",
    "AsyncPaginator",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "FieldError",
    "Flashpi",
    "FlashpiError",
    "InternalServerError",
    "Language",
    "NotFoundError",
    "Page",
    "PermissionDeniedError",
    "Problem",
    "RateLimitError",
    "RequestOptions",
    "UnprocessableEntityError",
    "WebhookHeaders",
    "WebhookPayload",
    "WebhookVerificationError",
    "WebhookVerificationReason",
    "Webhooks",
    "__version__",
    "unwrap_webhook",
    "verify_webhook_signature",
]
