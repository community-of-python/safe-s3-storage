import dataclasses
import typing

import botocore
import botocore.exceptions
import stamina
from types_aiobotocore_s3 import S3Client
from types_aiobotocore_s3.type_defs import GetObjectOutputTypeDef

from safe_s3_storage.exceptions import InvalidS3PathError
from safe_s3_storage.file_validator import ValidatedFile


_REQUIRED_S3_PATH_PARTS_COUNT: typing.Final = 2


def _extract_bucket_name_and_object_key(s3_path: str) -> tuple[str, str]:
    path_parts: typing.Final = tuple(s3_path.strip("/").split("/", 1))
    if len(path_parts) != _REQUIRED_S3_PATH_PARTS_COUNT:
        raise InvalidS3PathError(s3_path=s3_path)
    return path_parts


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UploadedFile(ValidatedFile):
    s3_path: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class S3Service:
    s3_client: S3Client
    max_retries: int = 3
    read_chunk_size: int = 70 * 1024

    async def upload_file(
        self,
        validated_file: ValidatedFile,
        *,
        bucket_name: str,
        object_key: str,
        metadata: dict[str, str] | None = None,
    ) -> UploadedFile:
        await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.max_retries)(self.s3_client.put_object)(
            Body=validated_file.file_content,
            Bucket=bucket_name,
            Key=object_key,
            ContentType=validated_file.mime_type,
            Metadata=metadata or {},
        )
        return UploadedFile(
            file_name=validated_file.file_name,
            file_content=validated_file.file_content,
            file_size=validated_file.file_size,
            mime_type=validated_file.mime_type,
            s3_path=f"{bucket_name}/{object_key}",
        )

    async def _retrieve_file_object(self, *, s3_path: str) -> GetObjectOutputTypeDef:
        bucket_name, object_key = _extract_bucket_name_and_object_key(s3_path)
        return await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.max_retries)(
            self.s3_client.get_object
        )(Bucket=bucket_name, Key=object_key)

    async def stream_file(self, *, s3_path: str) -> typing.AsyncIterator[bytes]:
        file_object: typing.Final = await self._retrieve_file_object(s3_path=s3_path)
        object_body: typing.Final = file_object["Body"]
        while one_chunk := await object_body.read(self.read_chunk_size):
            yield one_chunk

    async def read_file(self, *, s3_path: str) -> bytes:
        file_object: typing.Final = await self._retrieve_file_object(s3_path=s3_path)
        return await file_object["Body"].read()
