from collections.abc import Mapping
from typing import Any

from fastapi import Response as Response

class JSONResponse(Response):
    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        background: Any = None,
    ) -> None: ...
