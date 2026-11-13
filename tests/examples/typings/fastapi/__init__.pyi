"""The parts of FastAPI 0.12x (and Starlette) the README examples use, with their real signatures
(FastAPI is not a dependency of this repository). Pyright reads it through `stubPath`."""

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

class Headers(Mapping[str, str]):
    """Starlette's `starlette.datastructures.Headers`."""

class Request:
    @property
    def headers(self) -> Headers: ...
    async def body(self) -> bytes: ...

class Response:
    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: Any = None,
    ) -> None: ...

class FastAPI:
    def __init__(self, **kwargs: Any) -> None: ...
    def post(self, path: str, **kwargs: Any) -> Callable[[_F], _F]: ...
