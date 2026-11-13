"""Base of every resource: resources only declare their operations as `RequestSpec`s.

```python
class Documents(SyncAPIResource):
    def get(self, document_id: str, **options: Unpack[RequestOptions]) -> Document:
        return self._request(
            RequestSpec[Document](
                method="GET", path=path_of("/v1/documents/{}", document_id), options=options
            )
        )
```
"""

from typing import TypeVar

from ._http import AsyncEngine, RequestSpec, SyncEngine
from ._response import record_response

T = TypeVar("T")


class SyncAPIResource:
    """Base of the resources of `Flashpi`."""

    def __init__(self, engine: SyncEngine) -> None:
        self._engine = engine

    def _request(self, spec: RequestSpec[T]) -> T:
        """Sends the request (with its retries) and returns its data."""
        result = self._engine.request(spec)
        record_response(result)
        return result.data


class AsyncAPIResource:
    """Base of the resources of `AsyncFlashpi`."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def _request(self, spec: RequestSpec[T]) -> T:
        """Sends the request (with its retries) and returns its data."""
        result = await self._engine.request(spec)
        record_response(result)
        return result.data
