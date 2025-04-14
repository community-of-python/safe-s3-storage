import dataclasses
import typing

import botocore
import botocore.exceptions
import stamina
from types_aiobotocore_s3.type_defs import GetObjectOutputTypeDef

from safe_s3_storage.file_validator import ValidatedFile
from safe_s3_storage.s3_base import BaseS3Service, extract_bucket_name_and_object_key


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UploadedFile(ValidatedFile):
    s3_path: str


@dataclasses.dataclass(kw_only=True, frozen=True)
class SafeS3FilesReader(BaseS3Service):
    read_chunk_size: int = 70 * 1024

    async def _retrieve_file_object(self, *, s3_path: str) -> GetObjectOutputTypeDef:
        bucket_name, object_key = extract_bucket_name_and_object_key(s3_path)
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
