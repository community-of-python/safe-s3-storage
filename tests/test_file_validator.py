import random
import typing

import faker
import httpx
import pytest

from s3_safe_storage import exceptions
from s3_safe_storage.file_validator import FileValidator, ImageConversionMimeType
from s3_safe_storage.kaspersky_scan_engine import (
    KasperskyScanEngineClient,
    KasperskyScanEngineResponse,
    KasperskyScanEngineScanResult,
)
from tests.conftest import MIME_OCTET_STREAM, generate_binary_content


@pytest.fixture
def png_file() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"  # PNG signature
        b"\x00\x00\x00\r"  # IHDR chunk length
        b"IHDR"  # IHDR chunk type
        b"\x00\x00\x00\x01"  # width: 1
        b"\x00\x00\x00\x01"  # height: 1
        b"\x08"  # bit depth: 8
        b"\x06"  # color type: RGBA
        b"\x00"  # compression method
        b"\x00"  # filter method
        b"\x00"  # interlace method
        b"\x1f\x15\xc4\x89"  # CRC for IHDR
        b"\x00\x00\x00\x0a"  # IDAT chunk length
        b"IDAT"  # IDAT chunk type
        b"\x78\x9c\x63\x60\x00\x00\x00\x02\x00\x01"  # compressed image data (deflate)
        b"\x5d\xc6\x2d\xb4"  # CRC for IDAT
        b"\x00\x00\x00\x00"  # IEND chunk length
        b"IEND"  # IEND chunk type
        b"\xae\x42\x60\x82"  # CRC for IEND
    )


def get_mocked_kaspersky_scan_engine_client(*, ok_response: bool) -> KasperskyScanEngineClient:
    if ok_response:
        all_scan_results: typing.Final[list[KasperskyScanEngineScanResult]] = list(KasperskyScanEngineScanResult)
        all_scan_results.remove(KasperskyScanEngineScanResult.DETECT)
        scan_result = random.choice(all_scan_results)
    else:
        scan_result = KasperskyScanEngineScanResult.DETECT

    scan_response: typing.Final = KasperskyScanEngineResponse(scanResult=scan_result)
    return KasperskyScanEngineClient(
        httpx_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=scan_response.model_dump(mode="json")))
        )
    )


class TestFileValidator:
    async def test_fails_to_validate_mime_type(self, faker: faker.Faker) -> None:
        with pytest.raises(exceptions.UnsupportedMimeTypeError):
            await FileValidator(allowed_mime_types=["image/jpeg"]).validate_file(
                file_name=faker.file_name(), file_content=generate_binary_content(faker)
            )

    async def test_fails_to_validate_file_size(self, faker: faker.Faker) -> None:
        with pytest.raises(exceptions.TooLargeFileError):
            await FileValidator(allowed_mime_types=[MIME_OCTET_STREAM], max_file_size_bytes=0).validate_file(
                file_name=faker.file_name(), file_content=generate_binary_content(faker)
            )

    async def test_fails_to_validate_image_size(self, faker: faker.Faker, png_file: bytes) -> None:
        with pytest.raises(exceptions.TooLargeFileError):
            await FileValidator(allowed_mime_types=["image/png"], max_image_size_bytes=0).validate_file(
                file_name=faker.file_name(), file_content=png_file
            )

    async def test_fails_to_convert_image(self, faker: faker.Faker, png_file: bytes) -> None:
        with pytest.raises(exceptions.FailedToConvertImageError):
            await FileValidator(allowed_mime_types=["image/png"]).validate_file(
                file_name=faker.file_name(), file_content=png_file[:50]
            )

    @pytest.mark.parametrize("image_conversion_mime_type", list(ImageConversionMimeType))
    async def test_ok_image(
        self, faker: faker.Faker, png_file: bytes, image_conversion_mime_type: ImageConversionMimeType
    ) -> None:
        file_name: typing.Final = faker.file_name()

        validated_file: typing.Final = await FileValidator(
            allowed_mime_types=["image/png"], image_conversion_mime_type=image_conversion_mime_type
        ).validate_file(file_name=file_name, file_content=png_file)

        assert validated_file.file_name == file_name
        assert validated_file.file_content != png_file
        assert validated_file.file_size == len(validated_file.file_content)
        assert validated_file.mime_type == image_conversion_mime_type

    async def test_ok_not_image(self, faker: faker.Faker) -> None:
        file_name: typing.Final = faker.file_name()
        file_content: typing.Final = generate_binary_content(faker)

        validated_file: typing.Final = await FileValidator(allowed_mime_types=[MIME_OCTET_STREAM]).validate_file(
            file_name=file_name, file_content=file_content
        )

        assert validated_file.file_name == file_name
        assert validated_file.file_content == file_content
        assert validated_file.file_size == len(file_content)
        assert validated_file.mime_type == MIME_OCTET_STREAM

    @pytest.mark.parametrize("ok_response", [True, False])
    async def test_antivirus_skips_images(self, faker: faker.Faker, png_file: bytes, ok_response: bool) -> None:
        await FileValidator(
            kaspersky_scan_engine_client=get_mocked_kaspersky_scan_engine_client(ok_response=ok_response),
            allowed_mime_types=["image/png"],
        ).validate_file(file_name=faker.file_name(), file_content=png_file)

    async def test_antivirus_fails(self, faker: faker.Faker) -> None:
        with pytest.raises(exceptions.ThreatDetectedError):
            await FileValidator(
                kaspersky_scan_engine_client=get_mocked_kaspersky_scan_engine_client(ok_response=False),
                allowed_mime_types=[MIME_OCTET_STREAM],
            ).validate_file(file_name=faker.file_name(), file_content=generate_binary_content(faker))

    async def test_antivirus_passes(self, faker: faker.Faker) -> None:
        await FileValidator(
            kaspersky_scan_engine_client=get_mocked_kaspersky_scan_engine_client(ok_response=True),
            allowed_mime_types=[MIME_OCTET_STREAM],
        ).validate_file(file_name=faker.file_name(), file_content=generate_binary_content(faker))
