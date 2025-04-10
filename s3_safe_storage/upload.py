import dataclasses
import enum
import typing

import botocore
import botocore.exceptions
import httpx
import magic
import pyvips  # type: ignore[import-untyped]
import stamina
from types_aiobotocore_s3 import S3Client

from s3_safe_storage.exceptions import FailedToConvertImageError, TooLargeFileError, UnsupportedMimeTypeError


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
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
    mime_type: str


class ImageConversionFormat(enum.StrEnum):
    jpeg = "image/jpeg"
    webp = "image/webp"


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _ImageConversionResult:
    file_content: bytes
    mime_type: str


class S3FilesUploader:
    httpx_client: httpx.AsyncClient
    s3_client: S3Client

    s3_bucket_name: str

    kaspersky_scan_engine_url: str = "http://127.0.0.1:9998/api/v3.0/scanmemory"
    kaspersky_scan_engine_timeout_seconds: int = 10000
    image_conversion_mime_type: ImageConversionFormat = ImageConversionFormat.jpeg
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

    def _validate_file_size(self, *, file_name: str, file_content: bytes, mime_type: str) -> None:
        content_size: typing.Final = len(file_content)
        max_size: typing.Final = self.max_image_size_bytes if _is_image(mime_type) else self.max_file_size_bytes
        if content_size > max_size:
            raise TooLargeFileError(file_name=file_name, mime_type=mime_type, max_size=max_size)

    def _convert_image(self, *, file_name: str, file_content: bytes, mime_type: str) -> _ImageConversionResult | None:
        if not _is_image(mime_type):
            return None

        try:
            pyvips_image: typing.Final[pyvips.Image] = pyvips.Image.new_from_buffer(file_content, options="")
            new_file_content = (
                file_content
                if mime_type == self.image_conversion_mime_type
                else typing.cast("bytes", pyvips_image.write_to_buffer(".webp", Q=85))
            )
        except pyvips.Error as pyvips_error:
            raise FailedToConvertImageError(file_name=file_name, mime_type=mime_type) from pyvips_error

        return _ImageConversionResult(file_content=new_file_content, mime_type=self.image_conversion_mime_type)

    async def upload_file(self, *, file_name: str, file_content: bytes) -> UploadedFile:
        mime_type = self._validate_mime_type(file_name=file_name, file_content=file_content)
        self._validate_file_size(file_name=file_name, file_content=file_content, mime_type=mime_type)
        if conversion_result := self._convert_image(
            file_name=file_name, file_content=file_content, mime_type=mime_type
        ):
            file_content = conversion_result.file_content
            mime_type = conversion_result.mime_type

        file_context = UploadedFileContext(file_name=file_name, file_content=file_content, mime_type=mime_type)
        s3_key = self.s3_key_generator(file_context)

        await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.s3_retries)(self.s3_client.put_object)(
            Body=file_content,
            Bucket=self.s3_bucket_name,
            Key=s3_key,
            ContentType=mime_type,
            Metadata=self.s3_metadata_generator(file_context),
        )

        return UploadedFile(
            file_content=file_content,
            file_name=file_name,
            file_size=len(file_content),
            mime_type=mime_type,
            s3_path=f"{self.s3_bucket_name}/{s3_key}",
        )
