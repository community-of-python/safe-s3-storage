import typing
from unittest import mock

import faker

from safe_s3_storage.file_validator import FileValidator
from safe_s3_storage.s3_service import S3Service, UploadedFile
from tests.conftest import MIME_OCTET_STREAM, generate_binary_content


class TestS3ServiceUpload:
    async def test_ok_upload(self, faker: faker.Faker) -> None:
        s3_client_mock: typing.Final = mock.AsyncMock()
        file_name: typing.Final = faker.file_name()
        bucket_name: typing.Final = faker.pystr()
        file_content: typing.Final = generate_binary_content(faker)
        file_original_name_key: typing.Final = faker.pystr()

        validated_file: typing.Final = await FileValidator(allowed_mime_types=[MIME_OCTET_STREAM]).validate_file(
            file_name=file_name, file_content=file_content
        )
        uploaded_file: typing.Final = await S3Service(s3_client=s3_client_mock).upload_file(
            validated_file,
            bucket_name=bucket_name,
            object_key=validated_file.file_name,
            metadata={file_original_name_key: file_name},
        )

        assert uploaded_file == UploadedFile(
            file_content=file_content,
            file_name=file_name,
            file_size=len(file_content),
            mime_type=MIME_OCTET_STREAM,
            s3_path=f"{bucket_name}/{file_name}",
        )
        s3_client_mock.put_object.assert_called_once_with(
            Body=file_content,
            Bucket=bucket_name,
            Key=file_name,
            ContentType=MIME_OCTET_STREAM,
            Metadata={file_original_name_key: file_name},
        )
