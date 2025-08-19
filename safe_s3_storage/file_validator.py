import dataclasses
import enum
import typing

import puremagic
import pyvips  # type: ignore[import-untyped]

from safe_s3_storage import exceptions
from safe_s3_storage.kaspersky_scan_engine import KasperskyScanEngineClient


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class ValidatedFile:
    file_name: str
    file_content: bytes
    file_size: int
    mime_type: str


def _is_image(mime_type: str) -> bool:
    return mime_type.startswith("image/")


class ImageConversionFormat(str, enum.Enum):
    jpeg = enum.auto()
    webp = enum.auto()


_IMAGE_CONVERSION_FORMAT_TO_MIME_TYPE_AND_EXTENSION_MAP: typing.Final = {
    ImageConversionFormat.jpeg: ("image/jpeg", "jpg"),
    ImageConversionFormat.webp: ("image/webp", "webp"),
}


def _split_file_base_name_and_extensions(file_name: str) -> tuple[str, str | None]:
    split_result: typing.Final = file_name.rsplit(".", 1) or [file_name]
    return split_result[0], None if len(split_result) == 1 else split_result[1]


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class FileValidator:
    kaspersky_scan_engine: KasperskyScanEngineClient | None = None
    allowed_mime_types: list[str]
    scan_images_with_antivirus: bool = True
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    max_image_size_bytes: int = 50 * 1024 * 1024  # 50 MB
    image_conversion_format: ImageConversionFormat = ImageConversionFormat.webp
    image_quality: int = 85

    def _validate_mime_type(self, *, file_name: str, file_content: bytes) -> str:
        try:
            mime_type = puremagic.from_string(file_content, mime=True)
        except puremagic.PureError:
            # unlike python-magic, puremagic doesn't recognize if text is binary
            try:
                file_content.decode()
            except UnicodeDecodeError:
                mime_type = "application/octet-stream"
            else:
                mime_type = "text/plain"
        if mime_type in self.allowed_mime_types:
            return mime_type

        raise exceptions.NotAllowedMimeTypeError(
            file_name=file_name, mime_type=mime_type, allowed_mime_types=self.allowed_mime_types
        )

    def _validate_file_size(self, *, file_name: str, file_content: bytes, mime_type: str) -> int:
        content_size: typing.Final = len(file_content)
        max_size: typing.Final = self.max_image_size_bytes if _is_image(mime_type) else self.max_file_size_bytes
        if content_size > max_size:
            raise exceptions.TooLargeFileError(
                file_name=file_name, file_size=content_size, mime_type=mime_type, max_size=max_size
            )
        return content_size

    def _convert_image(self, validated_file: ValidatedFile) -> ValidatedFile:
        if not _is_image(validated_file.mime_type):
            return validated_file

        target_mime_type, target_extension = _IMAGE_CONVERSION_FORMAT_TO_MIME_TYPE_AND_EXTENSION_MAP[
            self.image_conversion_format
        ]

        try:
            pyvips_image: typing.Final[pyvips.Image] = pyvips.Image.new_from_buffer(
                validated_file.file_content, options=""
            )
            new_file_content: typing.Final = typing.cast(
                "bytes",
                pyvips_image.write_to_buffer(f".{target_extension}", Q=self.image_quality),
            )
        except pyvips.Error as pyvips_error:
            raise exceptions.FailedToConvertImageError(
                file_name=validated_file.file_name, mime_type=validated_file.mime_type
            ) from pyvips_error

        file_base_name, _file_extension = _split_file_base_name_and_extensions(validated_file.file_name)
        return ValidatedFile(
            file_name=f"{file_base_name}.{target_extension}",
            file_content=new_file_content,
            file_size=len(new_file_content),
            mime_type=target_mime_type,
        )

    async def validate_file(self, *, file_name: str, file_content: bytes) -> ValidatedFile:
        mime_type: typing.Final = self._validate_mime_type(file_name=file_name, file_content=file_content)
        file_size: typing.Final = self._validate_file_size(
            file_name=file_name, file_content=file_content, mime_type=mime_type
        )
        validated_file: typing.Final = self._convert_image(
            ValidatedFile(file_name=file_name, file_content=file_content, mime_type=mime_type, file_size=file_size)
        )
        if self.kaspersky_scan_engine:
            is_image: typing.Final = _is_image(validated_file.mime_type)
            if (is_image and self.scan_images_with_antivirus) or not is_image:
                await self.kaspersky_scan_engine.scan_memory(
                    file_name=validated_file.file_name, file_content=validated_file.file_content
                )
        return validated_file
