import dataclasses
import typing

from types_aiobotocore_s3 import S3Client

from s3_safe_storage.exceptions import InvalidFilePathError


REQUIRED_SEGMENT_COUNT: typing.Final = 2


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class BaseS3CRUD:
    s3_client: S3Client
    s3_bucket_name: str
    s3_retries: int = 3


def extract_bucket_name_and_object_key(file_path: str) -> tuple[str, str]:
    segments = tuple(file_path.strip("/").split("/", 1))
    if len(segments) != REQUIRED_SEGMENT_COUNT:
        raise InvalidFilePathError(file_path=file_path)
    return segments
