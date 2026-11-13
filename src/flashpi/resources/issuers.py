"""The issuers (RUCs) of the account, with their establishments, emission points and .p12
certificates. Needs an account-scoped API key with read_write access, also to read."""

from functools import cached_property
from typing import Unpack

from flashpi._http import AsyncEngine, RequestOptions, RequestSpec, SyncEngine, path_of
from flashpi._pagination import AsyncPaginator, ListBody, Page
from flashpi._resource import AsyncAPIResource, SyncAPIResource
from flashpi._response import async_response_wrapper, response_wrapper
from flashpi.resources.uploads import certificate_form
from flashpi.types import (
    Certificate,
    CertificateListParams,
    CertificateUpload,
    CreateEmissionPoint,
    CreateEstablishment,
    CreateIssuer,
    EmissionPoint,
    EmissionPointListParams,
    Establishment,
    EstablishmentListParams,
    Issuer,
    IssuerListParams,
    UpdateEstablishment,
    UpdateIssuer,
)

ISSUERS = "/v1/issuers"
ISSUER = "/v1/issuers/{}"
ESTABLISHMENTS = "/v1/issuers/{}/establishments"
ESTABLISHMENT = "/v1/issuers/{}/establishments/{}"
EMISSION_POINTS = "/v1/issuers/{}/establishments/{}/emission-points"
EMISSION_POINT = "/v1/issuers/{}/establishments/{}/emission-points/{}"
CERTIFICATES = "/v1/issuers/{}/certificates"
CERTIFICATE = "/v1/issuers/{}/certificates/{}"


# The operations, shared by both clients.


def create_issuer(body: CreateIssuer, options: RequestOptions) -> RequestSpec[Issuer]:
    return RequestSpec[Issuer](method="POST", path=ISSUERS, body=body, options=options)


def list_issuers(
    params: IssuerListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[Issuer]]:
    return RequestSpec[ListBody[Issuer]](method="GET", path=ISSUERS, query=params, options=options)


def get_issuer(issuer_id: str, options: RequestOptions) -> RequestSpec[Issuer]:
    return RequestSpec[Issuer](method="GET", path=path_of(ISSUER, issuer_id), options=options)


def update_issuer(
    issuer_id: str, body: UpdateIssuer, options: RequestOptions
) -> RequestSpec[Issuer]:
    path = path_of(ISSUER, issuer_id)
    return RequestSpec[Issuer](method="PATCH", path=path, body=body, options=options)


def delete_issuer(issuer_id: str, options: RequestOptions) -> RequestSpec[None]:
    path = path_of(ISSUER, issuer_id)
    return RequestSpec[None](method="DELETE", path=path, response_type="none", options=options)


def create_establishment(
    issuer_id: str, body: CreateEstablishment, options: RequestOptions
) -> RequestSpec[Establishment]:
    path = path_of(ESTABLISHMENTS, issuer_id)
    return RequestSpec[Establishment](method="POST", path=path, body=body, options=options)


def list_establishments(
    issuer_id: str, params: EstablishmentListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[Establishment]]:
    path = path_of(ESTABLISHMENTS, issuer_id)
    return RequestSpec[ListBody[Establishment]](
        method="GET", path=path, query=params, options=options
    )


def get_establishment(
    issuer_id: str, establishment_id: str, options: RequestOptions
) -> RequestSpec[Establishment]:
    path = path_of(ESTABLISHMENT, issuer_id, establishment_id)
    return RequestSpec[Establishment](method="GET", path=path, options=options)


def update_establishment(
    issuer_id: str, establishment_id: str, body: UpdateEstablishment, options: RequestOptions
) -> RequestSpec[Establishment]:
    path = path_of(ESTABLISHMENT, issuer_id, establishment_id)
    return RequestSpec[Establishment](method="PATCH", path=path, body=body, options=options)


def delete_establishment(
    issuer_id: str, establishment_id: str, options: RequestOptions
) -> RequestSpec[None]:
    path = path_of(ESTABLISHMENT, issuer_id, establishment_id)
    return RequestSpec[None](method="DELETE", path=path, response_type="none", options=options)


def create_emission_point(
    issuer_id: str, establishment_id: str, body: CreateEmissionPoint, options: RequestOptions
) -> RequestSpec[EmissionPoint]:
    path = path_of(EMISSION_POINTS, issuer_id, establishment_id)
    return RequestSpec[EmissionPoint](method="POST", path=path, body=body, options=options)


def list_emission_points(
    issuer_id: str,
    establishment_id: str,
    params: EmissionPointListParams | None,
    options: RequestOptions,
) -> RequestSpec[ListBody[EmissionPoint]]:
    path = path_of(EMISSION_POINTS, issuer_id, establishment_id)
    return RequestSpec[ListBody[EmissionPoint]](
        method="GET", path=path, query=params, options=options
    )


def get_emission_point(
    issuer_id: str, establishment_id: str, emission_point_id: str, options: RequestOptions
) -> RequestSpec[EmissionPoint]:
    path = path_of(EMISSION_POINT, issuer_id, establishment_id, emission_point_id)
    return RequestSpec[EmissionPoint](method="GET", path=path, options=options)


def delete_emission_point(
    issuer_id: str, establishment_id: str, emission_point_id: str, options: RequestOptions
) -> RequestSpec[None]:
    path = path_of(EMISSION_POINT, issuer_id, establishment_id, emission_point_id)
    return RequestSpec[None](method="DELETE", path=path, response_type="none", options=options)


def upload_certificate(
    issuer_id: str, upload: CertificateUpload, options: RequestOptions
) -> RequestSpec[Certificate]:
    path = path_of(CERTIFICATES, issuer_id)
    form = certificate_form(upload)
    return RequestSpec[Certificate](method="POST", path=path, multipart=form, options=options)


def list_certificates(
    issuer_id: str, params: CertificateListParams | None, options: RequestOptions
) -> RequestSpec[ListBody[Certificate]]:
    path = path_of(CERTIFICATES, issuer_id)
    return RequestSpec[ListBody[Certificate]](
        method="GET", path=path, query=params, options=options
    )


def get_certificate(
    issuer_id: str, certificate_id: str, options: RequestOptions
) -> RequestSpec[Certificate]:
    path = path_of(CERTIFICATE, issuer_id, certificate_id)
    return RequestSpec[Certificate](method="GET", path=path, options=options)


# Flashpi


class EmissionPoints(SyncAPIResource):
    """Emission points (the second 3-digit series code) of an establishment."""

    def create(
        self,
        issuer_id: str,
        establishment_id: str,
        body: CreateEmissionPoint,
        **options: Unpack[RequestOptions],
    ) -> EmissionPoint:
        return self._request(create_emission_point(issuer_id, establishment_id, body, options))

    def list(
        self,
        issuer_id: str,
        establishment_id: str,
        params: EmissionPointListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> Page[EmissionPoint]:
        """Lists the emission points of an establishment, by code."""
        return self._list(list_emission_points(issuer_id, establishment_id, params, options))

    def get(
        self,
        issuer_id: str,
        establishment_id: str,
        emission_point_id: str,
        **options: Unpack[RequestOptions],
    ) -> EmissionPoint:
        spec = get_emission_point(issuer_id, establishment_id, emission_point_id, options)
        return self._request(spec)

    def delete(
        self,
        issuer_id: str,
        establishment_id: str,
        emission_point_id: str,
        **options: Unpack[RequestOptions],
    ) -> None:
        spec = delete_emission_point(issuer_id, establishment_id, emission_point_id, options)
        return self._request(spec)

    @cached_property
    def with_response(self) -> "EmissionPointsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return EmissionPointsWithResponse(self)


class EmissionPointsWithResponse:
    def __init__(self, emission_points: EmissionPoints) -> None:
        self.create = response_wrapper(emission_points.create)
        self.list = response_wrapper(emission_points.list)
        self.get = response_wrapper(emission_points.get)
        self.delete = response_wrapper(emission_points.delete)


class Establishments(SyncAPIResource):
    """Establishments (the 3-digit series codes such as `001`) of an issuer."""

    emission_points: EmissionPoints
    """Emission points of an establishment."""

    def __init__(self, engine: SyncEngine) -> None:
        super().__init__(engine)
        self.emission_points = EmissionPoints(engine)

    def create(
        self, issuer_id: str, body: CreateEstablishment, **options: Unpack[RequestOptions]
    ) -> Establishment:
        return self._request(create_establishment(issuer_id, body, options))

    def list(
        self,
        issuer_id: str,
        params: EstablishmentListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> Page[Establishment]:
        """Lists the establishments of an issuer, by code."""
        return self._list(list_establishments(issuer_id, params, options))

    def get(
        self, issuer_id: str, establishment_id: str, **options: Unpack[RequestOptions]
    ) -> Establishment:
        return self._request(get_establishment(issuer_id, establishment_id, options))

    def update(
        self,
        issuer_id: str,
        establishment_id: str,
        body: UpdateEstablishment,
        **options: Unpack[RequestOptions],
    ) -> Establishment:
        return self._request(update_establishment(issuer_id, establishment_id, body, options))

    def delete(
        self, issuer_id: str, establishment_id: str, **options: Unpack[RequestOptions]
    ) -> None:
        return self._request(delete_establishment(issuer_id, establishment_id, options))

    @cached_property
    def with_response(self) -> "EstablishmentsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return EstablishmentsWithResponse(self)


class EstablishmentsWithResponse:
    def __init__(self, establishments: Establishments) -> None:
        self.create = response_wrapper(establishments.create)
        self.list = response_wrapper(establishments.list)
        self.get = response_wrapper(establishments.get)
        self.update = response_wrapper(establishments.update)
        self.delete = response_wrapper(establishments.delete)


class Certificates(SyncAPIResource):
    """The .p12 certificates (firmas electrónicas) of an issuer."""

    def upload(
        self, issuer_id: str, upload: CertificateUpload, **options: Unpack[RequestOptions]
    ) -> Certificate:
        """Uploads a .p12 for the issuer, for the mode of the API key only (test or live). To
        renew the certificate of both modes, start an `issuer_onboardings` with it instead.

        Flashpi checks it in the background: the certificate starts `processing`, then becomes
        `accepted` (event `certificate.verified`, or `certificate.pending` while its revocation
        status cannot be checked) or `rejected` (no event: follow it with `get()` and read
        `rejection`).
        """
        return self._request(upload_certificate(issuer_id, upload, options))

    def list(
        self,
        issuer_id: str,
        params: CertificateListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> Page[Certificate]:
        """Lists the certificates of an issuer, newest first."""
        return self._list(list_certificates(issuer_id, params, options))

    def get(
        self, issuer_id: str, certificate_id: str, **options: Unpack[RequestOptions]
    ) -> Certificate:
        return self._request(get_certificate(issuer_id, certificate_id, options))

    @cached_property
    def with_response(self) -> "CertificatesWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return CertificatesWithResponse(self)


class CertificatesWithResponse:
    def __init__(self, certificates: Certificates) -> None:
        self.upload = response_wrapper(certificates.upload)
        self.list = response_wrapper(certificates.list)
        self.get = response_wrapper(certificates.get)


class Issuers(SyncAPIResource):
    """The issuers (RUCs) of the account, with their establishments, emission points and .p12
    certificates. Needs an account-scoped API key with read_write access, also to read."""

    establishments: Establishments
    """Establishments of an issuer, with their emission points."""

    certificates: Certificates
    """The .p12 certificates of an issuer."""

    def __init__(self, engine: SyncEngine) -> None:
        super().__init__(engine)
        self.establishments = Establishments(engine)
        self.certificates = Certificates(engine)

    def create(self, body: CreateIssuer, **options: Unpack[RequestOptions]) -> Issuer:
        """Creates an issuer. To start from its .p12 instead, see `issuer_onboardings`."""
        return self._request(create_issuer(body, options))

    def list(
        self, params: IssuerListParams | None = None, **options: Unpack[RequestOptions]
    ) -> Page[Issuer]:
        """Lists the issuers, newest first."""
        return self._list(list_issuers(params, options))

    def get(self, issuer_id: str, **options: Unpack[RequestOptions]) -> Issuer:
        """Retrieves an issuer."""
        return self._request(get_issuer(issuer_id, options))

    def update(
        self, issuer_id: str, body: UpdateIssuer, **options: Unpack[RequestOptions]
    ) -> Issuer:
        """Updates an issuer's name, tax profile, branding or defaults (only the fields sent)."""
        return self._request(update_issuer(issuer_id, body, options))

    def delete(self, issuer_id: str, **options: Unpack[RequestOptions]) -> None:
        """Deletes an issuer that has no documents and no certificates, with its
        establishments, emission points and issuer-scoped API keys. Otherwise 409
        `resource_in_use`: certificates cannot be deleted, so an issuer that ever had a .p12
        (one from `issuer_onboardings` too) stays."""
        return self._request(delete_issuer(issuer_id, options))

    @cached_property
    def with_response(self) -> "IssuersWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return IssuersWithResponse(self)


class IssuersWithResponse:
    def __init__(self, issuers: Issuers) -> None:
        self.create = response_wrapper(issuers.create)
        self.list = response_wrapper(issuers.list)
        self.get = response_wrapper(issuers.get)
        self.update = response_wrapper(issuers.update)
        self.delete = response_wrapper(issuers.delete)


# AsyncFlashpi


class AsyncEmissionPoints(AsyncAPIResource):
    """Emission points (the second 3-digit series code) of an establishment."""

    async def create(
        self,
        issuer_id: str,
        establishment_id: str,
        body: CreateEmissionPoint,
        **options: Unpack[RequestOptions],
    ) -> EmissionPoint:
        spec = create_emission_point(issuer_id, establishment_id, body, options)
        return await self._request(spec)

    def list(
        self,
        issuer_id: str,
        establishment_id: str,
        params: EmissionPointListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> AsyncPaginator[EmissionPoint]:
        """Lists the emission points of an establishment, by code."""
        return self._list(list_emission_points(issuer_id, establishment_id, params, options))

    async def get(
        self,
        issuer_id: str,
        establishment_id: str,
        emission_point_id: str,
        **options: Unpack[RequestOptions],
    ) -> EmissionPoint:
        spec = get_emission_point(issuer_id, establishment_id, emission_point_id, options)
        return await self._request(spec)

    async def delete(
        self,
        issuer_id: str,
        establishment_id: str,
        emission_point_id: str,
        **options: Unpack[RequestOptions],
    ) -> None:
        spec = delete_emission_point(issuer_id, establishment_id, emission_point_id, options)
        return await self._request(spec)

    @cached_property
    def with_response(self) -> "AsyncEmissionPointsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncEmissionPointsWithResponse(self)


class AsyncEmissionPointsWithResponse:
    def __init__(self, emission_points: AsyncEmissionPoints) -> None:
        self.create = async_response_wrapper(emission_points.create)
        self.list = async_response_wrapper(emission_points.list)
        self.get = async_response_wrapper(emission_points.get)
        self.delete = async_response_wrapper(emission_points.delete)


class AsyncEstablishments(AsyncAPIResource):
    """Establishments (the 3-digit series codes such as `001`) of an issuer."""

    emission_points: AsyncEmissionPoints
    """Emission points of an establishment."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self.emission_points = AsyncEmissionPoints(engine)

    async def create(
        self, issuer_id: str, body: CreateEstablishment, **options: Unpack[RequestOptions]
    ) -> Establishment:
        return await self._request(create_establishment(issuer_id, body, options))

    def list(
        self,
        issuer_id: str,
        params: EstablishmentListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> AsyncPaginator[Establishment]:
        """Lists the establishments of an issuer, by code."""
        return self._list(list_establishments(issuer_id, params, options))

    async def get(
        self, issuer_id: str, establishment_id: str, **options: Unpack[RequestOptions]
    ) -> Establishment:
        return await self._request(get_establishment(issuer_id, establishment_id, options))

    async def update(
        self,
        issuer_id: str,
        establishment_id: str,
        body: UpdateEstablishment,
        **options: Unpack[RequestOptions],
    ) -> Establishment:
        spec = update_establishment(issuer_id, establishment_id, body, options)
        return await self._request(spec)

    async def delete(
        self, issuer_id: str, establishment_id: str, **options: Unpack[RequestOptions]
    ) -> None:
        return await self._request(delete_establishment(issuer_id, establishment_id, options))

    @cached_property
    def with_response(self) -> "AsyncEstablishmentsWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncEstablishmentsWithResponse(self)


class AsyncEstablishmentsWithResponse:
    def __init__(self, establishments: AsyncEstablishments) -> None:
        self.create = async_response_wrapper(establishments.create)
        self.list = async_response_wrapper(establishments.list)
        self.get = async_response_wrapper(establishments.get)
        self.update = async_response_wrapper(establishments.update)
        self.delete = async_response_wrapper(establishments.delete)


class AsyncCertificates(AsyncAPIResource):
    """The .p12 certificates (firmas electrónicas) of an issuer."""

    async def upload(
        self, issuer_id: str, upload: CertificateUpload, **options: Unpack[RequestOptions]
    ) -> Certificate:
        """Uploads a .p12 for the issuer, for the mode of the API key only (test or live). To
        renew the certificate of both modes, start an `issuer_onboardings` with it instead.

        Flashpi checks it in the background: the certificate starts `processing`, then becomes
        `accepted` (event `certificate.verified`, or `certificate.pending` while its revocation
        status cannot be checked) or `rejected` (no event: follow it with `get()` and read
        `rejection`).
        """
        return await self._request(upload_certificate(issuer_id, upload, options))

    def list(
        self,
        issuer_id: str,
        params: CertificateListParams | None = None,
        **options: Unpack[RequestOptions],
    ) -> AsyncPaginator[Certificate]:
        """Lists the certificates of an issuer, newest first."""
        return self._list(list_certificates(issuer_id, params, options))

    async def get(
        self, issuer_id: str, certificate_id: str, **options: Unpack[RequestOptions]
    ) -> Certificate:
        return await self._request(get_certificate(issuer_id, certificate_id, options))

    @cached_property
    def with_response(self) -> "AsyncCertificatesWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncCertificatesWithResponse(self)


class AsyncCertificatesWithResponse:
    def __init__(self, certificates: AsyncCertificates) -> None:
        self.upload = async_response_wrapper(certificates.upload)
        self.list = async_response_wrapper(certificates.list)
        self.get = async_response_wrapper(certificates.get)


class AsyncIssuers(AsyncAPIResource):
    """The issuers (RUCs) of the account, with their establishments, emission points and .p12
    certificates. Needs an account-scoped API key with read_write access, also to read."""

    establishments: AsyncEstablishments
    """Establishments of an issuer, with their emission points."""

    certificates: AsyncCertificates
    """The .p12 certificates of an issuer."""

    def __init__(self, engine: AsyncEngine) -> None:
        super().__init__(engine)
        self.establishments = AsyncEstablishments(engine)
        self.certificates = AsyncCertificates(engine)

    async def create(self, body: CreateIssuer, **options: Unpack[RequestOptions]) -> Issuer:
        """Creates an issuer. To start from its .p12 instead, see `issuer_onboardings`."""
        return await self._request(create_issuer(body, options))

    def list(
        self, params: IssuerListParams | None = None, **options: Unpack[RequestOptions]
    ) -> AsyncPaginator[Issuer]:
        """Lists the issuers, newest first."""
        return self._list(list_issuers(params, options))

    async def get(self, issuer_id: str, **options: Unpack[RequestOptions]) -> Issuer:
        """Retrieves an issuer."""
        return await self._request(get_issuer(issuer_id, options))

    async def update(
        self, issuer_id: str, body: UpdateIssuer, **options: Unpack[RequestOptions]
    ) -> Issuer:
        """Updates an issuer's name, tax profile, branding or defaults (only the fields sent)."""
        return await self._request(update_issuer(issuer_id, body, options))

    async def delete(self, issuer_id: str, **options: Unpack[RequestOptions]) -> None:
        """Deletes an issuer that has no documents and no certificates, with its
        establishments, emission points and issuer-scoped API keys. Otherwise 409
        `resource_in_use`: certificates cannot be deleted, so an issuer that ever had a .p12
        (one from `issuer_onboardings` too) stays."""
        return await self._request(delete_issuer(issuer_id, options))

    @cached_property
    def with_response(self) -> "AsyncIssuersWithResponse":
        """The same methods, returning an `APIResponse` with the HTTP response and request id."""
        return AsyncIssuersWithResponse(self)


class AsyncIssuersWithResponse:
    def __init__(self, issuers: AsyncIssuers) -> None:
        self.create = async_response_wrapper(issuers.create)
        self.list = async_response_wrapper(issuers.list)
        self.get = async_response_wrapper(issuers.get)
        self.update = async_response_wrapper(issuers.update)
        self.delete = async_response_wrapper(issuers.delete)
