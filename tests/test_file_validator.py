import random
import typing

import faker
import httpx2
import pydantic
import pytest
import pyvips  # type: ignore[import-untyped]
from httpx2 import codes as status_codes

from safe_s3_storage import exceptions
from safe_s3_storage.exceptions import KasperskyScanEngineConnectionStatusError
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
        b"\x00\x00\x00\x0b"  # IDAT chunk length
        b"IDAT"  # IDAT chunk type
        b"\x78\xda\x63\x60\x00\x02\x00\x00\x05\x00\x01"  # compressed image data (deflate)
        b"\xe9\xfa\xdc\xd8"  # CRC for IDAT
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
    return get_kaspersky_scan_engine_client_responding_with(
        faker=faker, status_code=status_codes.OK, json=scan_response.model_dump(mode="json")
    )


ScanEngineOutcome = int | type[httpx2.TransportError]


def get_kaspersky_scan_engine_client_with_outcomes(
    *, faker: faker.Faker, outcomes: list[ScanEngineOutcome], max_retries: int
) -> tuple[KasperskyScanEngineClient, list[httpx2.Request]]:
    requests: typing.Final[list[httpx2.Request]] = []
    clean_response: typing.Final = KasperskyScanEngineResponse(scanResult=KasperskyScanEngineScanResult.CLEAN)

    def respond(request: httpx2.Request) -> httpx2.Response:
        outcome: typing.Final = outcomes[len(requests)]
        requests.append(request)
        if not isinstance(outcome, int):
            raise outcome(faker.pystr(), request=request)
        if outcome == status_codes.OK:
            return httpx2.Response(outcome, json=clean_response.model_dump(mode="json"))
        return httpx2.Response(outcome, json="")

    client: typing.Final = KasperskyScanEngineClient(
        service_url=faker.url(schemes=["http"]),
        client_name=faker.pystr(),
        max_retries=max_retries,
        httpx_client=httpx2.AsyncClient(transport=httpx2.MockTransport(respond)),
    )
    return client, requests


def get_kaspersky_scan_engine_client_responding_with(
    *, faker: faker.Faker, status_code: int, json: object
) -> KasperskyScanEngineClient:
    return KasperskyScanEngineClient(
        service_url=faker.url(schemes=["http"]),
        client_name=faker.pystr(),
        httpx_client=httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda _: httpx2.Response(status_code, json=json)),
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

    async def test_all_mime_types_allowed(self, faker: faker.Faker) -> None:
        validated_file: typing.Final = await FileValidator(allowed_mime_types=None).validate_file(
            file_name=faker.file_name(), file_content=generate_binary_content(faker)
        )
        assert validated_file is not None

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

    @pytest.mark.parametrize("file_content", ["test'", "abracadabra", "python script"])
    async def test_txt_file_validate(self, file_content: str) -> None:
        file_name: typing.Final = "file_name.txt"

        validated_file: typing.Final = await FileValidator(allowed_mime_types=["text/plain"]).validate_file(
            file_name=file_name, file_content=file_content.encode()
        )

        assert validated_file.file_name == file_name
        assert validated_file.file_content == file_content.encode()
        assert validated_file.file_size == len(file_content)
        assert validated_file.mime_type == "text/plain"

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

    async def test_antivirus_no_connection(self, faker: faker.Faker, png_file: bytes) -> None:
        kasper: typing.Final = get_kaspersky_scan_engine_client_responding_with(
            faker=faker, status_code=status_codes.GATEWAY_TIMEOUT, json=""
        )
        with pytest.raises(KasperskyScanEngineConnectionStatusError):
            await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)

    async def test_antivirus_accepts_v3_0_non_scanned_reason(self, faker: faker.Faker, png_file: bytes) -> None:
        kasper: typing.Final = get_kaspersky_scan_engine_client_responding_with(
            faker=faker, status_code=status_codes.OK, json={"scanResult": "NON_SCANNED (PASSWORD PROTECTED)"}
        )
        await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)

    @pytest.mark.parametrize("response_json", [{"scanResult": "UNKNOWN"}, {}, ""])
    async def test_antivirus_invalid_response(self, faker: faker.Faker, png_file: bytes, response_json: object) -> None:
        kasper: typing.Final = get_kaspersky_scan_engine_client_responding_with(
            faker=faker, status_code=status_codes.OK, json=response_json
        )
        with pytest.raises(exceptions.KasperskyScanEngineInvalidResponseError) as exc_info:
            await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)
        assert isinstance(exc_info.value.__cause__, pydantic.ValidationError)

    @pytest.mark.parametrize("transport_error", [httpx2.ConnectError, httpx2.ReadTimeout])
    async def test_antivirus_transport_error(
        self, faker: faker.Faker, png_file: bytes, transport_error: type[httpx2.TransportError]
    ) -> None:
        def raise_transport_error(request: httpx2.Request) -> httpx2.Response:
            raise transport_error(faker.pystr(), request=request)

        kasper: typing.Final = KasperskyScanEngineClient(
            service_url=faker.url(schemes=["http"]),
            client_name=faker.pystr(),
            httpx_client=httpx2.AsyncClient(transport=httpx2.MockTransport(raise_transport_error)),
        )
        with pytest.raises(KasperskyScanEngineConnectionStatusError) as exc_info:
            await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)
        assert isinstance(exc_info.value.__cause__, transport_error)

    @pytest.mark.parametrize("failure", [httpx2.ConnectError, httpx2.ReadTimeout, status_codes.SERVICE_UNAVAILABLE])
    async def test_antivirus_retries_transient_failures(
        self, faker: faker.Faker, png_file: bytes, failure: ScanEngineOutcome
    ) -> None:
        kasper, requests = get_kaspersky_scan_engine_client_with_outcomes(
            faker=faker, outcomes=[failure, failure, status_codes.OK], max_retries=2
        )
        await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)
        assert len(requests) == 3  # noqa: PLR2004

    @pytest.mark.parametrize("max_retries", [0, 3])
    async def test_antivirus_gives_up_after_max_retries(
        self, faker: faker.Faker, png_file: bytes, max_retries: int
    ) -> None:
        kasper, requests = get_kaspersky_scan_engine_client_with_outcomes(
            faker=faker, outcomes=[status_codes.SERVICE_UNAVAILABLE] * (max_retries + 1), max_retries=max_retries
        )
        with pytest.raises(KasperskyScanEngineConnectionStatusError):
            await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)
        assert len(requests) == max_retries + 1

    async def test_antivirus_does_not_retry_client_errors(self, faker: faker.Faker, png_file: bytes) -> None:
        kasper, requests = get_kaspersky_scan_engine_client_with_outcomes(
            faker=faker, outcomes=[status_codes.BAD_REQUEST], max_retries=3
        )
        with pytest.raises(KasperskyScanEngineConnectionStatusError):
            await kasper.scan_memory(file_name=faker.file_name(), file_content=png_file)
        assert len(requests) == 1

    @pytest.mark.parametrize("image_conversion_format", list(ImageConversionFormat))
    async def test_excluded_conversion_formats(
        self, faker: faker.Faker, png_file: bytes, image_conversion_format: ImageConversionFormat
    ) -> None:
        file_base_name: typing.Final = faker.pystr()
        file_extension: typing.Final = faker.file_extension()
        validated_file: typing.Final = await FileValidator(
            allowed_mime_types=["image/png"],
            image_conversion_format=image_conversion_format,
            excluded_conversion_formats=[file_extension],
        ).validate_file(file_name=f"{file_base_name}.{file_extension}", file_content=png_file)

        assert validated_file.file_name == f"{file_base_name}.{file_extension}"
        assert validated_file.file_content == png_file
        assert validated_file.file_size == len(validated_file.file_content)

    async def test_conversion_does_not_leave_pyvips_operations_cached(
        self, faker: faker.Faker, png_file: bytes
    ) -> None:
        # libvips keeps a process-global operation cache; for one-shot conversions of
        # unique buffers it only retains memory. The validator must disable it so the
        # cache does not accumulate across conversions (memory leak).
        await FileValidator(allowed_mime_types=["image/png"]).validate_file(
            file_name=f"{faker.pystr()}.png", file_content=png_file
        )

        assert pyvips.cache_get_size() == 0
