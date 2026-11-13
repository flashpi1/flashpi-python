from collections.abc import Mapping
from typing import Any

class HttpHeaders(Mapping[str, str]):
    """A case-insensitive mapping of the request headers."""

class HttpRequest:
    @property
    def body(self) -> bytes: ...
    @property
    def headers(self) -> HttpHeaders: ...

class HttpResponse:
    def __init__(
        self,
        content: object = b"",
        content_type: str | None = None,
        status: int | None = None,
        reason: str | None = None,
        charset: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None: ...

class JsonResponse(HttpResponse):
    def __init__(
        self,
        data: Any,
        encoder: type[Any] = ...,
        safe: bool = True,
        json_dumps_params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None: ...
