"""Creating an issuer from its .p12 certificate."""

from functools import cached_property
from typing import Unpack

from flashpi._http import RequestOptions, RequestSpec, path_of
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import async_response_wrapper, response_wrapper
from flashpi.resources.uploads import certificate_form
from flashpi.types import (
    CertificateUpload,
    CompletedIssuerOnboarding,
    CompleteIssuerOnboarding,
    IssuerOnboarding,
)


def create_spec(
    upload: CertificateUpload, options: RequestOptions
) -> RequestSpec[IssuerOnboarding]:
    form = certificate_form(upload)
    return RequestSpec[IssuerOnboarding](
        method="POST", path="/v1/issuer-onboardings", multipart=form, options=options
    )


def get_spec(onboarding_id: str, options: RequestOptions) -> RequestSpec[IssuerOnboarding]:
    path = path_of("/v1/issuer-onboardings/{}", onboarding_id)
    return RequestSpec[IssuerOnboarding](method="GET", path=path, options=options)


def complete_spec(
    onboarding_id: str, body: CompleteIssuerOnboarding | None, options: RequestOptions
) -> RequestSpec[CompletedIssuerOnboarding]:
    path = path_of("/v1/issuer-onboardings/{}/complete", onboarding_id)
    return RequestSpec[CompletedIssuerOnboarding](
        method="POST", path=path, body={} if body is None else body, options=options
    )


class IssuerOnboardings(SyncAPIResource):
    """Creates an issuer from its .p12: upload the certificate, wait while the onboarding is
    `verifying` until it is `ready` (Flashpi reads the holder, RUC and SRI data) or `rejected`,
    review the prefill, then complete it.

    Needs an account-scoped API key with read_write access.
    """

    def create(
        self, upload: CertificateUpload, **options: Unpack[RequestOptions]
    ) -> IssuerOnboarding:
        """Starts an onboarding with a .p12 and its password. It starts `verifying`."""
        return self._request(create_spec(upload, options))

    def get(self, onboarding_id: str, **options: Unpack[RequestOptions]) -> IssuerOnboarding:
        """Retrieves an onboarding, to follow it while it is `verifying`."""
        return self._request(get_spec(onboarding_id, options))

    def complete(
        self,
        onboarding_id: str,
        body: CompleteIssuerOnboarding | None = None,
        **options: Unpack[RequestOptions],
    ) -> CompletedIssuerOnboarding:
        """Completes a `ready` onboarding.

        - For a new RUC, `body` is the issuer to create (as in `issuers.create()`): `legalName`,
          `headOfficeAddress` and `taxProfile` are required. Build it from
          `onboarding["prefill"]`; the API does not apply the prefill by itself.
        - When `onboarding["existingIssuer"]` is set, `body` can be left out (`{}` is sent): the
          certificate is added to that issuer for both modes (a renewal) and the issuer is left
          as it is.
        - Send `ruc` when `onboarding["rucNeedsConfirmation"]` is true.
        """
        return self._request(complete_spec(onboarding_id, body, options))

    @cached_property
    def with_response(self) -> "IssuerOnboardingsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return IssuerOnboardingsWithResponse(self)


class IssuerOnboardingsWithResponse:
    def __init__(self, onboardings: IssuerOnboardings) -> None:
        self.create = response_wrapper(onboardings.create)
        self.get = response_wrapper(onboardings.get)
        self.complete = response_wrapper(onboardings.complete)


class AsyncIssuerOnboardings(AsyncAPIResource):
    """Creates an issuer from its .p12, for `AsyncFlashpi`. See `IssuerOnboardings`."""

    async def create(
        self, upload: CertificateUpload, **options: Unpack[RequestOptions]
    ) -> IssuerOnboarding:
        """Starts an onboarding with a .p12 and its password. It starts `verifying`."""
        return await self._request(create_spec(upload, options))

    async def get(self, onboarding_id: str, **options: Unpack[RequestOptions]) -> IssuerOnboarding:
        """Retrieves an onboarding, to follow it while it is `verifying`."""
        return await self._request(get_spec(onboarding_id, options))

    async def complete(
        self,
        onboarding_id: str,
        body: CompleteIssuerOnboarding | None = None,
        **options: Unpack[RequestOptions],
    ) -> CompletedIssuerOnboarding:
        """Completes a `ready` onboarding. See `IssuerOnboardings.complete()`."""
        return await self._request(complete_spec(onboarding_id, body, options))

    @cached_property
    def with_response(self) -> "AsyncIssuerOnboardingsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncIssuerOnboardingsWithResponse(self)


class AsyncIssuerOnboardingsWithResponse:
    def __init__(self, onboardings: AsyncIssuerOnboardings) -> None:
        self.create = async_response_wrapper(onboardings.create)
        self.get = async_response_wrapper(onboardings.get)
        self.complete = async_response_wrapper(onboardings.complete)
