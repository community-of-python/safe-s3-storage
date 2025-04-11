import dataclasses

from types_aiobotocore_s3 import S3Client


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class BaseS3Service:
    s3_client: S3Client
    bucket_name: str
    max_retries: int = 3
