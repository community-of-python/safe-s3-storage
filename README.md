# safe-s3-storage

S3 tools for uploading files to S3 safely (antivirus check, etc) as well as downloading and deleting files.

## How To Use

```
uv add safe-s3-storage
poetry add safe-s3-storage
```

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
