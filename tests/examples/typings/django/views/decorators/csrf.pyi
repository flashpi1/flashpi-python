from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

def csrf_exempt(view_func: _F) -> _F: ...
