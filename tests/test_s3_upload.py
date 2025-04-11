import typing
from unittest import mock

import faker

from safe_s3_storage.file_validator import FileValidator
from safe_s3_storage.s3_upload import SafeS3FilesUploader, UploadedFile
from tests.conftest import MIME_OCTET_STREAM, generate_binary_content


class TestSafeS3FilesUploader:
    async def test_ok_with_defaults(self, faker: faker.Faker) -> None:
        s3_client_mock: typing.Final = mock.AsyncMock()
        file_name: typing.Final = faker.file_name()
        bucket_name: typing.Final = faker.pystr()
        file_content: typing.Final = generate_binary_content(faker)

        uploaded_file: typing.Final = await SafeS3FilesUploader(
            file_validator=FileValidator(allowed_mime_types=[MIME_OCTET_STREAM]),
            s3_client=s3_client_mock,
            bucket_name=bucket_name,
        ).upload_file(file_name=file_name, file_content=file_content)

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
            Metadata={},
        )

    async def test_ok_with_custom_key_generator(self, faker: faker.Faker) -> None:
        s3_client_mock: typing.Final = mock.AsyncMock()
        file_name: typing.Final = faker.file_name()
        file_name_prefix: typing.Final = faker.pystr()
        bucket_name: typing.Final = faker.pystr()

        uploaded_file: typing.Final = await SafeS3FilesUploader(
            file_validator=FileValidator(allowed_mime_types=[MIME_OCTET_STREAM]),
            s3_client=s3_client_mock,
            bucket_name=bucket_name,
            s3_key_generator=lambda file_context: file_name_prefix + file_context.file_name,
        ).upload_file(file_name=file_name, file_content=generate_binary_content(faker))

        assert uploaded_file.s3_path == f"{bucket_name}/{file_name_prefix}{file_name}"
        assert s3_client_mock.put_object.mock_calls[0].kwargs["Key"] == file_name_prefix + file_name

    async def test_ok_with_custom_metadata_generator(self, faker: faker.Faker) -> None:
        s3_client_mock: typing.Final = mock.AsyncMock()
        file_name: typing.Final = faker.file_name()
        file_original_name_key: typing.Final = faker.pystr()

        await SafeS3FilesUploader(
            file_validator=FileValidator(allowed_mime_types=[MIME_OCTET_STREAM]),
            s3_client=s3_client_mock,
            bucket_name=faker.pystr(),
            s3_metadata_generator=lambda file_context: {file_original_name_key: file_context.file_name},
        ).upload_file(file_name=file_name, file_content=generate_binary_content(faker))

        assert s3_client_mock.put_object.mock_calls[0].kwargs["Metadata"] == {file_original_name_key: file_name}
