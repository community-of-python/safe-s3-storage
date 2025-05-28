import random
import typing

import faker
import httpx
import pytest

from safe_s3_storage import exceptions
from safe_s3_storage.file_validator import (
    _IMAGE_CONVERSION_FORMAT_TO_MIME_TYPE_AND_EXTENSION_MAP,
    FileValidator,
    ImageConversionFormat,
)
from safe_s3_storage.kaspersky_scan_engine import (
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


def get_mocked_kaspersky_scan_engine_client(*, faker: faker.Faker, ok_response: bool) -> KasperskyScanEngineClient:
    if ok_response:
        all_scan_results: typing.Final[list[KasperskyScanEngineScanResult]] = list(KasperskyScanEngineScanResult)
        all_scan_results.remove(KasperskyScanEngineScanResult.DETECT)
        scan_result = random.choice(all_scan_results)
    else:
        scan_result = KasperskyScanEngineScanResult.DETECT

    scan_response: typing.Final = KasperskyScanEngineResponse(scanResult=scan_result)
    return KasperskyScanEngineClient(
        service_url=faker.url(schemes=["http"]),
        client_name=faker.pystr(),
        httpx_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=scan_response.model_dump(mode="json")))
        ),
    )


class TestFileValidator:
    async def test_fails_to_validate_mime_type(self, faker: faker.Faker) -> None:
        with pytest.raises(exceptions.NotAllowedMimeTypeError):
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

    @pytest.mark.parametrize("image_conversion_format", list(ImageConversionFormat))
    async def test_ok_image(
        self, faker: faker.Faker, png_file: bytes, image_conversion_format: ImageConversionFormat
    ) -> None:
        file_base_name: typing.Final = faker.pystr()

        validated_file: typing.Final = await FileValidator(
            allowed_mime_types=["image/png"], image_conversion_format=image_conversion_format
        ).validate_file(file_name=f"{file_base_name}.{faker.file_extension()}", file_content=png_file)

        assert (
            validated_file.file_name
            == f"{file_base_name}.{_IMAGE_CONVERSION_FORMAT_TO_MIME_TYPE_AND_EXTENSION_MAP[image_conversion_format][1]}"
        )
        assert validated_file.file_content != png_file
        assert validated_file.file_size == len(validated_file.file_content)
        assert (
            validated_file.mime_type
            == _IMAGE_CONVERSION_FORMAT_TO_MIME_TYPE_AND_EXTENSION_MAP[image_conversion_format][0]
        )

    @pytest.mark.parametrize("binary", [True, False])
    async def test_ok_not_image(self, faker: faker.Faker, binary: bool) -> None:
        file_name: typing.Final = faker.file_name()
        file_content: typing.Final = generate_binary_content(faker) if binary else faker.pystr().encode()

        validated_file: typing.Final = await FileValidator(
            allowed_mime_types=[MIME_OCTET_STREAM if binary else "text/plain"]
        ).validate_file(file_name=file_name, file_content=file_content)

        assert validated_file.file_name == file_name
        assert validated_file.file_content == file_content
        assert validated_file.file_size == len(file_content)
        assert validated_file.mime_type == MIME_OCTET_STREAM if binary else "text/plain"

    @pytest.mark.parametrize("ok_response", [True, False])
    async def test_antivirus_skips_images(self, faker: faker.Faker, png_file: bytes, ok_response: bool) -> None:
        await FileValidator(
            kaspersky_scan_engine=get_mocked_kaspersky_scan_engine_client(faker=faker, ok_response=ok_response),
            scan_images_with_antivirus=False,
            allowed_mime_types=["image/png"],
        ).validate_file(file_name=faker.file_name(), file_content=png_file)

    async def test_antivirus_fails_on_files(self, faker: faker.Faker) -> None:
        with pytest.raises(exceptions.KasperskyScanEngineThreatDetectedError):
            await FileValidator(
                kaspersky_scan_engine=get_mocked_kaspersky_scan_engine_client(faker=faker, ok_response=False),
                allowed_mime_types=[MIME_OCTET_STREAM],
            ).validate_file(file_name=faker.file_name(), file_content=generate_binary_content(faker))

    async def test_antivirus_fails_on_images(self, faker: faker.Faker, png_file: bytes) -> None:
        with pytest.raises(exceptions.KasperskyScanEngineThreatDetectedError):
            await FileValidator(
                kaspersky_scan_engine=get_mocked_kaspersky_scan_engine_client(faker=faker, ok_response=False),
                allowed_mime_types=["image/png"],
            ).validate_file(file_name=faker.file_name(), file_content=png_file)

    async def test_antivirus_passes_on_files(self, faker: faker.Faker) -> None:
        await FileValidator(
            kaspersky_scan_engine=get_mocked_kaspersky_scan_engine_client(faker=faker, ok_response=True),
            allowed_mime_types=[MIME_OCTET_STREAM],
        ).validate_file(file_name=faker.file_name(), file_content=generate_binary_content(faker))

    async def test_antivirus_passes_on_images(self, faker: faker.Faker, png_file: bytes) -> None:
        await FileValidator(
            kaspersky_scan_engine=get_mocked_kaspersky_scan_engine_client(faker=faker, ok_response=True),
            allowed_mime_types=["image/png"],
        ).validate_file(file_name=faker.file_name(), file_content=png_file)
