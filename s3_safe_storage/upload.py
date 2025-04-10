import typing

import httpx
from types_aiobotocore_s3 import S3Client


class UploadedFile:
    file_content: bytes
    file_name: str
    file_size: int
    mime_type: str
    s3_path: str


class S3FilesUploader:
    httpx_client: httpx.AsyncClient
    s3_client: S3Client

    kaspersky_scan_engine_url: str = "http://127.0.0.1:9998/api/v3.0/scanmemory"
    kaspersky_scan_engine_timeout_seconds: int = 10000
    image_conversion_format: typing.Literal["jpeg", "webp"] = "webp"
    allowed_mime_types_to_file_extensions: dict[str, list[str]]
    max_file_size_bytes: int
    max_image_size_bytes: int
    temporary_upload_url_expires_seconds: int = 3600
    validate_s3_file_metadata_before_get_or_delete: typing.Callable[[dict[str, str]], None] | None = None

    async def upload_file(self, *, file_content: bytes, file_name: str, metadata: dict[str, str]) -> UploadedFile: ...
