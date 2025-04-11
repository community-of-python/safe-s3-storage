import dataclasses
import typing

import botocore
import botocore.exceptions
import stamina

from safe_s3_storage.file_validator import FileValidator, ValidatedFile
from safe_s3_storage.s3_base import BaseS3Service


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class UploadedFile(ValidatedFile):
    s3_path: str


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class SafeS3FilesUploader(BaseS3Service):
    file_validator: FileValidator
    s3_key_generator: typing.Callable[[ValidatedFile], str] = lambda file_context: file_context.file_name
    s3_metadata_generator: typing.Callable[[ValidatedFile], typing.Mapping[str, str]] = lambda _file_context: {}

    async def upload_file(self, *, file_name: str, file_content: bytes) -> UploadedFile:
        validated_file: typing.Final = await self.file_validator.validate_file(
            file_name=file_name, file_content=file_content
        )
        s3_key: typing.Final = self.s3_key_generator(validated_file)

        await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.max_retries)(self.s3_client.put_object)(
            Body=validated_file.file_content,
            Bucket=self.bucket_name,
            Key=s3_key,
            ContentType=validated_file.mime_type,
            Metadata=self.s3_metadata_generator(validated_file),
        )

        return UploadedFile(
            file_name=validated_file.file_name,
            file_content=validated_file.file_content,
            file_size=validated_file.file_size,
            mime_type=validated_file.mime_type,
            s3_path=f"{self.bucket_name}/{s3_key}",
        )
