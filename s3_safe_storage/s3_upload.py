import dataclasses
import typing

import botocore
import botocore.exceptions
import stamina

from s3_safe_storage.file_validator import FileValidator, ValidatedFile
from s3_safe_storage.s3_base import BaseS3CRUD


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UploadedFile:
    file_content: bytes
    file_name: str
    file_size: int
    mime_type: str
    s3_path: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UploadedFileContext:
    file_name: str
    file_content: bytes
    mime_type: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class S3FilesUploader(BaseS3CRUD):
    file_validator: FileValidator
    s3_key_generator: typing.Callable[[ValidatedFile], str] = lambda file_context: file_context.file_name
    s3_metadata_generator: typing.Callable[[ValidatedFile], typing.Mapping[str, str]] = lambda _file_context: {}

    async def upload_file(self, *, file_name: str, file_content: bytes) -> UploadedFile:
        validated_file = await self.file_validator.validate_file(file_name=file_name, file_content=file_content)
        s3_key = self.s3_key_generator(validated_file)

        await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.s3_retries)(self.s3_client.put_object)(
            Body=validated_file.file_content,
            Bucket=self.s3_bucket_name,
            Key=s3_key,
            ContentType=validated_file.mime_type,
            Metadata=self.s3_metadata_generator(validated_file),
        )

        return UploadedFile(
            file_content=validated_file.file_content,
            file_name=validated_file.file_name,
            file_size=validated_file.file_size,
            mime_type=validated_file.mime_type,
            s3_path=f"{self.s3_bucket_name}/{s3_key}",
        )
