"""Which uploads are accepted."""

from io import BytesIO

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from core.errors import ValidationError
from services.documents import validate_upload


def upload(filename: str, content_type: str) -> UploadFile:
    return UploadFile(
        file=BytesIO(b""),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def test_empty_file_is_rejected():
    with pytest.raises(ValidationError, match="empty"):
        validate_upload(upload("notes.txt", "text/plain"), 0)


def test_oversized_file_is_rejected(settings_override):
    settings_override(MAX_UPLOAD_BYTES=10)

    with pytest.raises(ValidationError, match="too large"):
        validate_upload(upload("notes.txt", "text/plain"), 11)


def test_unsupported_type_is_rejected():
    with pytest.raises(ValidationError, match="PDF and TXT"):
        validate_upload(upload("evil.exe", "application/octet-stream"), 100)


def test_text_file_is_accepted():
    validate_upload(upload("notes.txt", "text/plain"), 100)


def test_extension_is_enough_when_the_content_type_is_generic():
    validate_upload(upload("report.pdf", "application/octet-stream"), 100)
