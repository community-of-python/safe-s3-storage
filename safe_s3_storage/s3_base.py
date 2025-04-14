import dataclasses
import typing

from types_aiobotocore_s3 import S3Client

from safe_s3_storage.exceptions import InvalidS3PathError


@dataclasses.dataclass(kw_only=True, frozen=True)
class BaseS3Service:
    s3_client: S3Client
    max_retries: int = 3


_REQUIRED_S3_PATH_PARTS_COUNT: typing.Final = 2


def extract_bucket_name_and_object_key(s3_path: str) -> tuple[str, str]:
    path_parts: typing.Final = tuple(s3_path.strip("/").split("/", 1))
    if len(path_parts) != _REQUIRED_S3_PATH_PARTS_COUNT:
        raise InvalidS3PathError(s3_path=s3_path)
    return path_parts
