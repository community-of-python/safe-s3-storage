import dataclasses
import enum
import typing

import puremagic
import pyvips  # type: ignore[import-untyped]

from safe_s3_storage.exceptions import FailedToConvertImageError, TooLargeFileError, UnsupportedMimeTypeError
from safe_s3_storage.kaspersky_scan_engine import KasperskyScanEngineClient


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
        try:
            mime_type = puremagic.from_string(file_content, mime=True)
        except puremagic.PureError:
            # puremagic unlike python-magic doesn't recognize if text is binary
            try:
                file_content.decode()
            except UnicodeDecodeError:
                mime_type = "application/octet-stream"
            else:
                mime_type = "text/plain"
        if mime_type in self.allowed_mime_types:
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

    def _convert_image(self, validated_file: ValidatedFile) -> ValidatedFile:
        if not _is_image(validated_file.mime_type):
            return validated_file

        try:
            pyvips_image: typing.Final[pyvips.Image] = pyvips.Image.new_from_buffer(
                validated_file.file_content, options=""
            )
            new_file_content: typing.Final = typing.cast(
                "bytes",
                pyvips_image.write_to_buffer(
                    _IMAGE_CONVERSION_FORMAT_TO_PYVIPS_EXTENSION[self.image_conversion_mime_type], Q=self.image_quality
                ),
            )
        except pyvips.Error as pyvips_error:
            raise FailedToConvertImageError(
                file_name=validated_file.file_name, mime_type=validated_file.mime_type
            ) from pyvips_error

        return ValidatedFile(
            file_name=validated_file.file_name,
            file_content=new_file_content,
            file_size=len(new_file_content),
            mime_type=self.image_conversion_mime_type,
        )

    async def validate_file(self, *, file_name: str, file_content: bytes) -> ValidatedFile:
        mime_type: typing.Final = self._validate_mime_type(file_name=file_name, file_content=file_content)
        file_size: typing.Final = self._validate_file_size(
            file_name=file_name, file_content=file_content, mime_type=mime_type
        )
        validated_file: typing.Final = self._convert_image(
            ValidatedFile(file_name=file_name, file_content=file_content, mime_type=mime_type, file_size=file_size)
        )
        if self.kaspersky_scan_engine_client and not _is_image(validated_file.mime_type):
            await self.kaspersky_scan_engine_client.scan_memory(file_content=validated_file.file_content)
        return validated_file
