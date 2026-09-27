# safe-s3-storage

S3 tools for uploading files to S3 safely (antivirus check, etc.) as well as downloading and deleting files.

## How To Use

```
uv add safe-s3-storage
poetry add safe-s3-storage
```

MIME type detection uses [python-magic](https://github.com/ahupp/python-magic), which needs the `libmagic` system library (for example, `apt install libmagic-dev` on Debian or Ubuntu, `brew install libmagic` on macOS).

## Quickstart

`FileValidator` checks the MIME type and size of a file, converts images to WebP (or JPEG), and optionally scans the result with Kaspersky Scan Engine. `S3Service` uploads the validated file and reads, links to or deletes it later.

```python
import datetime
import typing

import aioboto3
import httpx2

from safe_s3_storage import FileValidator, KasperskyScanEngineClient, S3Service, UploadedFile


async def upload_avatar(*, file_name: str, file_content: bytes) -> UploadedFile:
    async with (
        httpx2.AsyncClient() as httpx_client,
        aioboto3.Session().client("s3", endpoint_url="http://localhost:9000") as s3_client,
    ):
        file_validator: typing.Final = FileValidator(
            allowed_mime_types=["image/png", "image/jpeg"],
            kaspersky_scan_engine=KasperskyScanEngineClient(
                httpx_client=httpx_client,
                service_url="http://kaspersky-scan-engine/api/v3.1/scanmemory",
                client_name="my-service",
            ),
        )
        validated_file: typing.Final = await file_validator.validate_file(
            file_name=file_name, file_content=file_content
        )

        s3_service: typing.Final = S3Service(s3_client=s3_client)
        uploaded_file: typing.Final = await s3_service.upload_file(
            validated_file, bucket_name="avatars", object_key=validated_file.file_name
        )

        file_url: typing.Final = await s3_service.create_file_url(
            s3_path=uploaded_file.s3_path,
            display_file_name=uploaded_file.file_name,
            expires_in=datetime.timedelta(hours=1),
        )
        print(file_url)
        return uploaded_file
```

- `KasperskyScanEngineClient` needs an [`httpx2`](https://github.com/pydantic/httpx2) `AsyncClient`. Passing an `httpx.AsyncClient` is not supported.
- `kaspersky_scan_engine` is optional. Without it, files are not scanned.
- `S3Service` also provides `read_file`, `stream_file`, `collect_file_head` and `delete_file`, each taking the `s3_path` from `UploadedFile`.

### Errors

Every error raised by the library subclasses `safe_s3_storage.exceptions.BaseError`:

| Error | Raised when |
|---|---|
| `NotAllowedMimeTypeError` | The detected MIME type is not in `allowed_mime_types`. |
| `TooLargeFileError` | The file exceeds `max_file_size_bytes`, or `max_image_size_bytes` for images. |
| `FailedToConvertImageError` | The image cannot be decoded or converted, for example because it is truncated. |
| `KasperskyScanEngineThreatDetectedError` | Kaspersky Scan Engine reports a threat. |
| `KasperskyScanEngineConnectionStatusError` | Kaspersky Scan Engine responds with a non-2xx status. |
| `InvalidS3PathError` | An `s3_path` is not in `bucket/key` form. |
| `FailedToReplaceS3BaseUrlWithProxyBaseUrlError` | `create_file_url` cannot swap the S3 endpoint for `proxy_base_url`. |

## Retries on S3 errors

safe-s3-storage doesn't provide any retries on S3 errors. You should configure in `S3Client`:

```python
import typing

import aioboto3
from aiobotocore.config import AioConfig
from types_aiobotocore_s3 import S3Client

from application.settings import settings


async def create_s3_resource() -> typing.AsyncIterator[S3Client]:
    s3_session: typing.Final = aioboto3.Session(
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
    )
    async with s3_session.client(
        "s3",
        endpoint_url=str(settings.s3_endpoint_url),
        config=AioConfig(retries={"max_attempts": 3, "mode": "standard"}),
    ) as s3_client:
        yield s3_client
```
