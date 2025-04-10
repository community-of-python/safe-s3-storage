import dataclasses
import typing

import botocore
import botocore.exceptions
import httpx
import magic
import stamina
from types_aiobotocore_s3 import S3Client

from s3_safe_storage.exceptions import TooLargeFileError, UnsupportedMimeTypeError


class UploadedFile:
    file_content: bytes
    file_name: str
    file_size: int
    mime_type: str
    s3_path: str


def _is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UploadedFileContext:
    file_name: str
    file_content: bytes
    content_size: int
    mime_type: str


class S3FilesUploader:
    httpx_client: httpx.AsyncClient
    s3_client: S3Client

    s3_bucket_name: str

    kaspersky_scan_engine_url: str = "http://127.0.0.1:9998/api/v3.0/scanmemory"
    kaspersky_scan_engine_timeout_seconds: int = 10000
    image_conversion_format: typing.Literal["jpeg", "webp"] = "webp"
    allowed_mime_types: list[str]
    max_file_size_bytes: int
    max_image_size_bytes: int
    s3_key_generator: typing.Callable[[UploadedFileContext], str] = lambda file_context: file_context.file_name
    s3_metadata_generator: typing.Callable[[UploadedFileContext], typing.Mapping[str, str]] = lambda _file_context: {}
    s3_retries: int = 3

    def _validate_mime_type(self, *, file_name: str, file_content: bytes) -> str:
        if (mime_type := magic.from_buffer(file_content, mime=True)) in self.allowed_mime_types:
            return mime_type
        raise UnsupportedMimeTypeError(
            file_name=file_name, mime_type=mime_type, allowed_mime_types=self.allowed_mime_types
        )

    def _validate_file_size(self, *, file_name: str, file_content: bytes, mime_type: str) -> int:
        content_size: typing.Final = len(file_content)
        max_size: typing.Final = self.max_image_size_bytes if _is_image(mime_type) else self.max_file_size_bytes
        if content_size > max_size:
            raise TooLargeFileError(file_name=file_name, mime_type=mime_type, max_size=max_size)
        return content_size

    async def upload_file(self, *, file_name: str, file_content: bytes) -> UploadedFile:
        mime_type = self._validate_mime_type(file_name=file_name, file_content=file_content)
        content_size = self._validate_file_size(file_name=file_name, file_content=file_content, mime_type=mime_type)
        file_context = UploadedFileContext(
            file_name=file_name,
            file_content=file_content,
            content_size=content_size,
            mime_type=mime_type,
        )
        await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.s3_retries)(self.s3_client.put_object)(
            Body=file_content,
            Bucket=self.s3_bucket_name,
            Key=self.s3_key_generator(file_context),
            ContentType=mime_type,
            Metadata=self.s3_metadata_generator(file_context),
        )
        return UploadedFile()
