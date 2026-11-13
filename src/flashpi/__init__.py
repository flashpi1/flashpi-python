"""The official Python SDK for Flashpi, the electronic invoicing API for Ecuador's SRI."""

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
from ._version import VERSION
from .types import ApiErrorCode, ApiFieldErrorCode, FieldError, Problem

__version__ = VERSION

__all__ = [
    "VERSION",
    "APIConnectionError",
    "APIError",
    "APITimeoutError",
    "ApiErrorCode",
    "ApiFieldErrorCode",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "FieldError",
    "FlashpiError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "Problem",
    "RateLimitError",
    "UnprocessableEntityError",
    "WebhookVerificationError",
    "WebhookVerificationReason",
    "__version__",
]
