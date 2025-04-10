import dataclasses
import enum
import typing

import magic
import pyvips  # type: ignore[import-untyped]

from s3_safe_storage.exceptions import FailedToConvertImageError, TooLargeFileError, UnsupportedMimeTypeError
from s3_safe_storage.kaspersky_scan_engine import KasperskyScanEngineClient


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ValidatedFile:
    file_name: str
    file_content: bytes
    file_size: int
    mime_type: str


def _is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


class ImageConversionMimeType(enum.StrEnum):
    jpeg = "image/jpeg"
    webp = "image/webp"


_IMAGE_CONVERSION_FORMAT_TO_PYVIPS_EXTENSION: typing.Final = {
    ImageConversionMimeType.jpeg: ".jpg",
    ImageConversionMimeType.webp: ".webp",
}


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class _ImageConversionResult:
    file_content: bytes
    mime_type: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class FileValidator:
    kaspersky_scan_engine_client: KasperskyScanEngineClient | None = None
    image_conversion_mime_type: ImageConversionMimeType = ImageConversionMimeType.webp
    allowed_mime_types: list[str]
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_image_size_bytes: int = 50 * 1024 * 1024
    image_quality: int = 85

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
            new_file_content = typing.cast(
                "bytes",
                pyvips_image.write_to_buffer(
                    _IMAGE_CONVERSION_FORMAT_TO_PYVIPS_EXTENSION[self.image_conversion_mime_type], Q=self.image_quality
                ),
            )
        except pyvips.Error as pyvips_error:
            raise FailedToConvertImageError(file_name=file_name, mime_type=mime_type) from pyvips_error

        return _ImageConversionResult(file_content=new_file_content, mime_type=self.image_conversion_mime_type)

    async def validate_file(self, *, file_name: str, file_content: bytes) -> ValidatedFile:
        mime_type = self._validate_mime_type(file_name=file_name, file_content=file_content)
        self._validate_file_size(file_name=file_name, file_content=file_content, mime_type=mime_type)
        if conversion_result := self._convert_image(
            file_name=file_name, file_content=file_content, mime_type=mime_type
        ):
            file_content = conversion_result.file_content
            mime_type = conversion_result.mime_type
        if self.kaspersky_scan_engine_client and not _is_image(mime_type):
            await self.kaspersky_scan_engine_client.scan_memory(file_content=file_content)
        return ValidatedFile(
            file_content=file_content,
            file_name=file_name,
            file_size=len(file_content),
            mime_type=mime_type,
        )
