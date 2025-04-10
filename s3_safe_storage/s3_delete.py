import dataclasses

import botocore.exceptions
import stamina

from s3_safe_storage.exceptions import S3FileNotFoundError
from s3_safe_storage.file_validator import FileValidator
from s3_safe_storage.s3_base import BaseS3CRUD, extract_bucket_name_and_object_key


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class S3FilesDeleter(BaseS3CRUD):
    file_validator: FileValidator

    async def delete_file(self, *, file_path: str) -> None:
        bucket_name, object_key = extract_bucket_name_and_object_key(file_path=file_path)
        try:
            await stamina.retry(on=botocore.exceptions.BotoCoreError, attempts=self.s3_retries)(
                self.s3_client.delete_object
            )(Bucket=bucket_name, Key=object_key)
        except botocore.exceptions.BotoCoreError as boto_error:
            raise S3FileNotFoundError(file_path=file_path) from boto_error
