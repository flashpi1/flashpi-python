"""The URLs Flashpi sends events to, and the deliveries of those events. Needs an account-scoped
API key with read_write access. To check the signature of a webhook you receive, use
`client.webhooks` instead."""

from functools import cached_property
from typing import Unpack

from flashpi._http import AsyncEngine, RequestOptions, RequestSpec, SyncEngine, path_of
from flashpi._pagination import AsyncPaginator, ListBody, Page
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import async_response_wrapper, response_wrapper
from flashpi.types import (
    CreateWebhookEndpoint,
    RotateWebhookEndpointSecret,
    UpdateWebhookEndpoint,
    WebhookDelivery,
    WebhookDeliveryDetail,
    WebhookDeliveryListParams,
    WebhookEndpoint,
    WebhookEndpointListParams,
    WebhookEndpointSecret,
)

ENDPOINTS = "/v1/webhook-endpoints"
ENDPOINT = "/v1/webhook-endpoints/{}"
DELIVERIES = "/v1/webhook-endpoints/{}/deliveries"
DELIVERY = "/v1/webhook-endpoints/{}/deliveries/{}"


# The operations, shared by both clients.


def create_endpoint(
    body: CreateWebhookEndpoint, options: RequestOptions
) -> RequestSpec[WebhookEndpoint]:
    return RequestSpec[WebhookEndpoint](method="POST", path=ENDPOINTS, body=body, options=options)


def list_endpoints(
    params: WebhookEndpointListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[WebhookEndpoint]]:
    return RequestSpec[ListBody[WebhookEndpoint]](
        method="GET", path=ENDPOINTS, query=params, options=options
    )


def get_endpoint(endpoint_id: str, options: RequestOptions) -> RequestSpec[WebhookEndpoint]:
    path = path_of(ENDPOINT, endpoint_id)
    return RequestSpec[WebhookEndpoint](method="GET", path=path, options=options)


def update_endpoint(
    endpoint_id: str, body: UpdateWebhookEndpoint, options: RequestOptions
) -> RequestSpec[WebhookEndpoint]:
    path = path_of(ENDPOINT, endpoint_id)
    return RequestSpec[WebhookEndpoint](method="PATCH", path=path, body=body, options=options)


def delete_endpoint(endpoint_id: str, options: RequestOptions) -> RequestSpec[None]:
    path = path_of(ENDPOINT, endpoint_id)
    return RequestSpec[None](method="DELETE", path=path, response_type="none", options=options)


def get_secret(endpoint_id: str, options: RequestOptions) -> RequestSpec[WebhookEndpointSecret]:
    path = path_of(f"{ENDPOINT}/secret", endpoint_id)
    return RequestSpec[WebhookEndpointSecret](method="GET", path=path, options=options)


def rotate_secret(
    endpoint_id: str, body: RotateWebhookEndpointSecret | None, options: RequestOptions
) -> RequestSpec[WebhookEndpoint]:
    path = path_of(f"{ENDPOINT}/rotate-secret", endpoint_id)
    return RequestSpec[WebhookEndpoint](method="POST", path=path, body=body, options=options)


def verify_endpoint(endpoint_id: str, options: RequestOptions) -> RequestSpec[WebhookEndpoint]:
    path = path_of(f"{ENDPOINT}/verify", endpoint_id)
    return RequestSpec[WebhookEndpoint](method="POST", path=path, options=options)


def list_deliveries(
    endpoint_id: str, params: WebhookDeliveryListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[WebhookDelivery]]:
    path = path_of(DELIVERIES, endpoint_id)
    return RequestSpec[ListBody[WebhookDelivery]](
        method="GET", path=path, query=params, options=options
    )


def get_delivery(
    endpoint_id: str, delivery_id: str, options: RequestOptions
) -> RequestSpec[WebhookDeliveryDetail]:
    path = path_of(DELIVERY, endpoint_id, delivery_id)
    return RequestSpec[WebhookDeliveryDetail](method="GET", path=path, options=options)


def replay_delivery(
    endpoint_id: str, delivery_id: str, options: RequestOptions
) -> RequestSpec[WebhookDeliveryDetail]:
    path = path_of(f"{DELIVERY}/replay", endpoint_id, delivery_id)
    return RequestSpec[WebhookDeliveryDetail](method="POST", path=path, options=options)


# Flashpi


class WebhookDeliveries(SyncAPIResource):
    """Deliveries of events to one endpoint."""

    def list(
        self,
        endpoint_id: str,
        params: WebhookDeliveryListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> Page[WebhookDelivery]:
        """Lists deliveries, newest first, optionally by status, event type or event."""
        return self._list(list_deliveries(endpoint_id, params, options))

    def get(
        self, endpoint_id: str, delivery_id: str, **options: Unpack[RequestOptions]
    ) -> WebhookDeliveryDetail:
        """Retrieves a delivery with its attempts."""
        return self._request(get_delivery(endpoint_id, delivery_id, options))

    def replay(
        self, endpoint_id: str, delivery_id: str, **options: Unpack[RequestOptions]
    ) -> WebhookDeliveryDetail:
        """Sends the delivery's event again, with the same `webhook-id`."""
        return self._request(replay_delivery(endpoint_id, delivery_id, options))

    @cached_property
    def with_response(self) -> "WebhookDeliveriesWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return WebhookDeliveriesWithResponse(self)


class WebhookDeliveriesWithResponse:
    def __init__(self, deliveries: WebhookDeliveries) -> None:
        self.list = response_wrapper(deliveries.list)
        self.get = response_wrapper(deliveries.get)
        self.replay = response_wrapper(deliveries.replay)


class WebhookEndpoints(SyncAPIResource):
    """The URLs Flashpi sends events to. Needs an account-scoped API key with read_write access.
    To check the signature of a webhook you receive, use `client.webhooks` instead."""

    deliveries: WebhookDeliveries
    """The deliveries of an endpoint: attempts, answers and manual replays."""

    def __init__(self, engine: SyncEngine) -> None:
        super().__init__(engine)
        self.deliveries = WebhookDeliveries(engine)

    def create(
        self, body: CreateWebhookEndpoint, **options: Unpack[RequestOptions]
    ) -> WebhookEndpoint:
        """Creates an endpoint. It stays `pending_verification` until it answers the activation
        challenge; read its secret with `get_secret()` first, then call `verify()` if needed."""
        return self._request(create_endpoint(body, options))

    def list(
        self, params: WebhookEndpointListParams | None = None, **options: Unpack[RequestOptions]
    ) -> Page[WebhookEndpoint]:
        """Lists the endpoints, newest first."""
        return self._list(list_endpoints(params, options))

    def get(self, endpoint_id: str, **options: Unpack[RequestOptions]) -> WebhookEndpoint:
        """Retrieves an endpoint."""
        return self._request(get_endpoint(endpoint_id, options))

    def update(
        self, endpoint_id: str, body: UpdateWebhookEndpoint, **options: Unpack[RequestOptions]
    ) -> WebhookEndpoint:
        """Updates the URL, events, payload mode, description or `disabled` (only the fields
        sent)."""
        return self._request(update_endpoint(endpoint_id, body, options))

    def delete(self, endpoint_id: str, **options: Unpack[RequestOptions]) -> None:
        """Deletes an endpoint."""
        return self._request(delete_endpoint(endpoint_id, options))

    def get_secret(
        self, endpoint_id: str, **options: Unpack[RequestOptions]
    ) -> WebhookEndpointSecret:
        """The signing secret (`whsec_...`) and, during a rotation, when the previous one
        expires."""
        return self._request(get_secret(endpoint_id, options))

    def rotate_secret(
        self,
        endpoint_id: str,
        body: RotateWebhookEndpointSecret | None = None,
        **options: Unpack[RequestOptions],
    ) -> WebhookEndpoint:
        """Replaces the signing secret. The previous one keeps signing for
        `previousSecretExpiresInHours` (24 by default, 0 to drop it at once). Read the new
        secret with `get_secret()`."""
        return self._request(rotate_secret(endpoint_id, body, options))

    def verify(self, endpoint_id: str, **options: Unpack[RequestOptions]) -> WebhookEndpoint:
        """Sends the activation challenge (`webhook_endpoint.verification`) to the endpoint
        again."""
        return self._request(verify_endpoint(endpoint_id, options))

    @cached_property
    def with_response(self) -> "WebhookEndpointsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return WebhookEndpointsWithResponse(self)


class WebhookEndpointsWithResponse:
    def __init__(self, endpoints: WebhookEndpoints) -> None:
        self.create = response_wrapper(endpoints.create)
        self.list = response_wrapper(endpoints.list)
        self.get = response_wrapper(endpoints.get)
        self.update = response_wrapper(endpoints.update)
        self.delete = response_wrapper(endpoints.delete)
        self.get_secret = response_wrapper(endpoints.get_secret)
        self.rotate_secret = response_wrapper(endpoints.rotate_secret)
        self.verify = response_wrapper(endpoints.verify)


# AsyncFlashpi


class AsyncWebhookDeliveries(AsyncAPIResource):
    """Deliveries of events to one endpoint."""

    def list(
        self,
        endpoint_id: str,
        params: WebhookDeliveryListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> AsyncPaginator[WebhookDelivery]:
        """Lists deliveries, newest first, optionally by status, event type or event."""
        return self._list(list_deliveries(endpoint_id, params, options))

    async def get(
        self, endpoint_id: str, delivery_id: str, **options: Unpack[RequestOptions]
    ) -> WebhookDeliveryDetail:
        """Retrieves a delivery with its attempts."""
        return await self._request(get_delivery(endpoint_id, delivery_id, options))

    async def replay(
        self, endpoint_id: str, delivery_id: str, **options: Unpack[RequestOptions]
    ) -> WebhookDeliveryDetail:
        """Sends the delivery's event again, with the same `webhook-id`."""
        return await self._request(replay_delivery(endpoint_id, delivery_id, options))

    @cached_property
    def with_response(self) -> "AsyncWebhookDeliveriesWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncWebhookDeliveriesWithResponse(self)


class AsyncWebhookDeliveriesWithResponse:
    def __init__(self, deliveries: AsyncWebhookDeliveries) -> None:
        self.list = async_response_wrapper(deliveries.list)
        self.get = async_response_wrapper(deliveries.get)
        self.replay = async_response_wrapper(deliveries.replay)


class AsyncWebhookEndpoints(AsyncAPIResource):
    """The URLs Flashpi sends events to. Needs an account-scoped API key with read_write access.
    To check the signature of a webhook you receive, use `client.webhooks` instead."""

    deliveries: AsyncWebhookDeliveries
    """The deliveries of an endpoint: attempts, answers and manual replays."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self.deliveries = AsyncWebhookDeliveries(engine)

    async def create(
        self, body: CreateWebhookEndpoint, **options: Unpack[RequestOptions]
    ) -> WebhookEndpoint:
        """Creates an endpoint. It stays `pending_verification` until it answers the activation
        challenge; read its secret with `get_secret()` first, then call `verify()` if needed."""
        return await self._request(create_endpoint(body, options))

    def list(
        self, params: WebhookEndpointListParams | None = None, **options: Unpack[RequestOptions]
    ) -> AsyncPaginator[WebhookEndpoint]:
        """Lists the endpoints, newest first."""
        return self._list(list_endpoints(params, options))

    async def get(self, endpoint_id: str, **options: Unpack[RequestOptions]) -> WebhookEndpoint:
        """Retrieves an endpoint."""
        return await self._request(get_endpoint(endpoint_id, options))

    async def update(
        self, endpoint_id: str, body: UpdateWebhookEndpoint, **options: Unpack[RequestOptions]
    ) -> WebhookEndpoint:
        """Updates the URL, events, payload mode, description or `disabled` (only the fields
        sent)."""
        return await self._request(update_endpoint(endpoint_id, body, options))

    async def delete(self, endpoint_id: str, **options: Unpack[RequestOptions]) -> None:
        """Deletes an endpoint."""
        return await self._request(delete_endpoint(endpoint_id, options))

    async def get_secret(
        self, endpoint_id: str, **options: Unpack[RequestOptions]
    ) -> WebhookEndpointSecret:
        """The signing secret (`whsec_...`) and, during a rotation, when the previous one
        expires."""
        return await self._request(get_secret(endpoint_id, options))

    async def rotate_secret(
        self,
        endpoint_id: str,
        body: RotateWebhookEndpointSecret | None = None,
        **options: Unpack[RequestOptions],
    ) -> WebhookEndpoint:
        """Replaces the signing secret. The previous one keeps signing for
        `previousSecretExpiresInHours` (24 by default, 0 to drop it at once). Read the new
        secret with `get_secret()`."""
        return await self._request(rotate_secret(endpoint_id, body, options))

    async def verify(self, endpoint_id: str, **options: Unpack[RequestOptions]) -> WebhookEndpoint:
        """Sends the activation challenge (`webhook_endpoint.verification`) to the endpoint
        again."""
        return await self._request(verify_endpoint(endpoint_id, options))

    @cached_property
    def with_response(self) -> "AsyncWebhookEndpointsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncWebhookEndpointsWithResponse(self)


class AsyncWebhookEndpointsWithResponse:
    def __init__(self, endpoints: AsyncWebhookEndpoints) -> None:
        self.create = async_response_wrapper(endpoints.create)
        self.list = async_response_wrapper(endpoints.list)
        self.get = async_response_wrapper(endpoints.get)
        self.update = async_response_wrapper(endpoints.update)
        self.delete = async_response_wrapper(endpoints.delete)
        self.get_secret = async_response_wrapper(endpoints.get_secret)
        self.rotate_secret = async_response_wrapper(endpoints.rotate_secret)
        self.verify = async_response_wrapper(endpoints.verify)
