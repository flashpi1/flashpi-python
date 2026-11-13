from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

def require_POST(func: _F) -> _F: ...  # noqa: N802 (Django's name)
