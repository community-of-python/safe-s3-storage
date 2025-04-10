import dataclasses
import typing

from types_aiobotocore_s3 import S3Client


REQUIRED_SEGMENT_COUNT: typing.Final = 2


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class BaseS3Service:
    s3_client: S3Client
    s3_bucket_name: str
    s3_retries: int = 3
