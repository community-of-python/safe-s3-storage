import dataclasses
import typing

import httpx
import magic
from types_aiobotocore_s3 import S3Client


class UploadedFile:
    file_content: bytes
    file_name: str
    file_size: int
    mime_type: str
    s3_path: str


@dataclasses.dataclass
class UnsupportedMimeTypeError(Exception):
    file_name: str
    mime_type: str
    allowed_mime_types: list[str]


@dataclasses.dataclass
class TooLargeFileError(Exception):
    file_name: str
    mime_type: str
    max_size: int


def _is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


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
    temporary_upload_url_expires_seconds: int = 3600
    validate_s3_file_metadata_before_get_or_delete: typing.Callable[[dict[str, str]], None] | None = None
    s3_path_generator: typing.Callable[[str], str] = lambda file_name: file_name

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

    async def upload_file(self, *, file_name: str, file_content: bytes, metadata: dict[str, str]) -> UploadedFile:
        mime_type = self._validate_mime_type(file_name=file_name, file_content=file_content)
        content_size = self._validate_file_size(file_name=file_name, file_content=file_content, mime_type=mime_type)

        try:
            await self.s3_client.put_object(
                Body=file_content,
                Bucket=self.s3_bucket_name,
                Key=file_struct.s3_file_name,
                ContentType=file_struct.mime,
                Metadata={"original_name": parse.quote(original_name)},
            )
        except boto_exceptions.BotoCoreError as exc:
            raise exceptions.FileUploadError(
                detail=(
                    rf"Unable to s3 upload {file_struct.name} to "
                    rf"{settings.s3settings.public_bucket}/{file_struct.s3_file_name}"
                ),
            ) from exc
        return UploadedFile()
