"""The multipart body of a .p12 upload, for `issuers.certificates.upload()` and
`issuer_onboardings.create()`."""

from collections.abc import Mapping
from typing import cast

from flashpi._errors import FlashpiError
from flashpi._http import Multipart
from flashpi.types import CertificateUpload

MAX_CERTIFICATE_BYTES = 1_048_576
"""Largest .p12 the API accepts (413 `payload_too_large` above it)."""

DEFAULT_FILENAME = "certificate.p12"
CONTENT_TYPE = "application/x-pkcs12"


def certificate_form(upload: CertificateUpload) -> Multipart:
    """The multipart body of a .p12 upload: one `file` part and one `password` field.

    The file is read once here, so every retry sends the same bytes (a file object could not be
    read twice). Raises before anything is sent: FlashpiError for a password that is not text, an
    empty file or one over 1 MiB, TypeError for a file that is neither bytes nor a binary file.
    """
    members = cast("object", upload)
    if not isinstance(members, Mapping):
        raise TypeError("The certificate upload must be a dict with file and password")
    fields = cast("Mapping[str, object]", members)
    password = fields.get("password")
    if not isinstance(password, str):
        raise FlashpiError("The certificate password must be a string")
    content = _read(fields.get("file"))
    if not content:
        raise FlashpiError("The certificate file is empty")
    if len(content) > MAX_CERTIFICATE_BYTES:
        raise FlashpiError(
            f"The certificate file has {len(content)} bytes; the API accepts up to "
            f"{MAX_CERTIFICATE_BYTES}"
        )
    filename = fields.get("filename")
    if filename is None:
        filename = DEFAULT_FILENAME
    elif not isinstance(filename, str):
        raise TypeError("The certificate filename must be a string")
    return Multipart(
        fields={"password": password}, files={"file": (filename, content, CONTENT_TYPE)}
    )


def _read(file: object) -> bytes:
    """The bytes of the file: bytes-like values as they are, file objects read to the end."""
    if isinstance(file, bytes | bytearray | memoryview):
        return bytes(cast("bytes | bytearray | memoryview[int]", file))
    read = getattr(file, "read", None)
    content = read() if callable(read) else None
    if not isinstance(content, bytes):
        raise TypeError(
            "The certificate file must be bytes or a file opened in binary mode ('rb'), "
            f"got {type(file).__name__}"
        )
    return content
