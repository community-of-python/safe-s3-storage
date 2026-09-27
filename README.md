# safe-s3-storage

Validates files before they reach S3 and manages them once they are there. Validation checks the file type and size, converts images to WebP or JPEG, and can scan files with Kaspersky Scan Engine. Stored files can be read, streamed, linked to with presigned URLs and deleted.

## Installation

With uv:

```bash
uv add safe-s3-storage
```

With Poetry:

```bash
poetry add safe-s3-storage
```

File type detection uses [python-magic](https://github.com/ahupp/python-magic), which needs the `libmagic` system library: `apt install libmagic-dev` on Debian or Ubuntu, `brew install libmagic` on macOS.

## Quickstart

Create the clients once, when your application starts, and reuse them for every upload:

```python
import contextlib
import typing
import uuid

import aioboto3
import httpx2
from aiobotocore.config import AioConfig

from safe_s3_storage import FileValidator, KasperskyScanEngineClient, S3Service, UploadedFile


@contextlib.asynccontextmanager
async def create_storage() -> typing.AsyncIterator[tuple[FileValidator, S3Service]]:
    async with (
        httpx2.AsyncClient(timeout=15.0) as httpx_client,
        aioboto3.Session().client(
            "s3",
            endpoint_url="http://localhost:9000",
            config=AioConfig(retries={"max_attempts": 3, "mode": "standard"}),
        ) as s3_client,
    ):
        file_validator: typing.Final = FileValidator(
            allowed_mime_types=["image/png", "image/jpeg", "application/pdf"],
            kaspersky_scan_engine=KasperskyScanEngineClient(
                httpx_client=httpx_client,
                service_url="http://kaspersky-scan-engine/api/v3.1/scanmemory",
                client_name="my-service",
                timeout_ms=10_000,
            ),
        )
        yield file_validator, S3Service(s3_client=s3_client)


async def upload_file(
    file_validator: FileValidator, s3_service: S3Service, *, file_name: str, file_content: bytes
) -> UploadedFile:
    validated_file: typing.Final = await file_validator.validate_file(file_name=file_name, file_content=file_content)
    return await s3_service.upload_file(validated_file, bucket_name="uploads", object_key=str(uuid.uuid4()))
```

The object key is generated so that uploads never overwrite each other and users don't choose S3 keys. Store `uploaded_file.s3_path` and `uploaded_file.file_name` to find and name the file later.

`aioboto3.Session()` reads credentials from the usual AWS sources, such as environment variables. Pass `aws_access_key_id` and `aws_secret_access_key` to it to set them explicitly.

### Kaspersky Scan Engine

`kaspersky_scan_engine` is optional; without it, files are not scanned. `KasperskyScanEngineClient` needs an [`httpx2`](https://github.com/pydantic/httpx2) `AsyncClient`.

Use the `/api/v3.1/scanmemory` endpoint. The v3.0 endpoint also works, but it ignores the `name` field.

Files that Scan Engine reports as `NON_SCANNED` or `SERVER_ERROR` are rejected with `KasperskyScanEngineNotScannedError`, because they were never checked. Password-protected archives, for example, come back as `NON_SCANNED`. Pass `allow_unscanned_files=True` to `KasperskyScanEngineClient` to accept them anyway.

Otherwise, only `CLEAN` results are accepted. `DISINFECTED` and `DELETED` mean Scan Engine found a threat in its copy of the file, while safe-s3-storage would store the original, so they raise `KasperskyScanEngineThreatDetectedError` like `DETECT`.

`timeout_ms` is the scan timeout sent to Scan Engine. The HTTP client has its own timeout, 5 seconds by default in httpx2, so set it above `timeout_ms` as in the example. Otherwise slow scans fail on the client side first.

### Retries

`KasperskyScanEngineClient` retries a scan up to `max_retries` times (3 by default) when Scan Engine can't be reached, times out or responds with a 5xx status. It retries immediately, without a delay. 4xx responses and scan results, including detected threats, are never retried. Set `max_retries=0` to turn retries off.

With retries, one scan can take up to `max_retries + 1` times the HTTP client timeout before `KasperskyScanEngineConnectionStatusError` is raised.

safe-s3-storage doesn't retry S3 requests. Configure S3 retries on the S3 client with `AioConfig`, as in the example.

## Validation

`FileValidator.validate_file` runs these steps in order:

1. Detects the MIME type from the file content and checks it against `allowed_mime_types`. With `None`, every type is allowed.
2. Checks the size of the original file against `max_image_size_bytes` for images and `max_file_size_bytes` for everything else.
3. Converts every `image/*` file to `image_conversion_format` and changes its extension to match, unless the file's extension is in `excluded_conversion_formats`.
4. Scans the converted file with Kaspersky Scan Engine, if configured. Images are skipped when `scan_images_with_antivirus` is `False`.

| Option | Default |
|---|---|
| `allowed_mime_types` | `None` (any type) |
| `max_file_size_bytes` | 10 MiB |
| `max_image_size_bytes` | 50 MiB |
| `image_conversion_format` | `ImageConversionFormat.webp` |
| `image_quality` | 85 |
| `excluded_conversion_formats` | `None`; list extensions without the dot, such as `["gif"]` |
| `kaspersky_scan_engine` | `None` (no scanning) |
| `scan_images_with_antivirus` | `True` |

## Reading and linking to files

The other `S3Service` methods take the `s3_path` from `UploadedFile`, in `bucket/key` form:

```python
import datetime
import typing

from safe_s3_storage import S3Service, UploadedFile


async def create_download_url(s3_service: S3Service, uploaded_file: UploadedFile) -> str:
    return await s3_service.create_file_url(
        s3_path=uploaded_file.s3_path,
        display_file_name=uploaded_file.file_name,
        expires_in=datetime.timedelta(hours=1),
    )


async def read_and_delete(s3_service: S3Service, uploaded_file: UploadedFile) -> bytes:
    file_content: typing.Final = await s3_service.read_file(s3_path=uploaded_file.s3_path)
    await s3_service.delete_file(s3_path=uploaded_file.s3_path)
    return file_content
```

`stream_file` yields the file in chunks, and `collect_file_head` returns its S3 metadata.

When S3 sits behind a proxy, pass `proxy_base_url` to `create_file_url`. The S3 endpoint at the start of the presigned URL is replaced with it.

## Errors

The library raises these errors, all subclasses of `safe_s3_storage.exceptions.BaseError`:

| Error | Raised when |
|---|---|
| `NotAllowedMimeTypeError` | The detected MIME type is not in `allowed_mime_types`. |
| `TooLargeFileError` | The file exceeds `max_file_size_bytes`, or `max_image_size_bytes` for images. |
| `FailedToConvertImageError` | The image can't be decoded or converted, for example because it is truncated. |
| `KasperskyScanEngineThreatDetectedError` | Kaspersky Scan Engine reports `DETECT`, `DISINFECTED` or `DELETED`. |
| `KasperskyScanEngineNotScannedError` | Kaspersky Scan Engine reports `NON_SCANNED` or `SERVER_ERROR`, unless `allow_unscanned_files=True`. |
| `KasperskyScanEngineInvalidResponseError` | Kaspersky Scan Engine returns a response body the library doesn't recognize. The pydantic error is chained as `__cause__`. |
| `KasperskyScanEngineConnectionStatusError` | Kaspersky Scan Engine can't be reached, times out or responds with a non-2xx status, after any retries. The httpx2 error is chained as `__cause__`. |
| `InvalidS3PathError` | An `s3_path` is not in `bucket/key` form. |
| `FailedToReplaceS3BaseUrlWithProxyBaseUrlError` | `create_file_url` can't find the S3 endpoint in the presigned URL to replace it with `proxy_base_url`. |

S3 failures reach you unwrapped, as botocore's `ClientError` and `BotoCoreError`.
