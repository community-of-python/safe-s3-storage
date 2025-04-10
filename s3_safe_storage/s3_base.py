import dataclasses

from types_aiobotocore_s3 import S3Client


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class BaseS3CRUD:
    s3_client: S3Client
    s3_bucket_name: str
    s3_retries: int = 3
