import typing
from unittest import mock

import faker
import pytest

from safe_s3_storage.exceptions import InvalidS3PathError
from safe_s3_storage.s3_service import SafeS3FilesService
from tests.conftest import generate_binary_content


class TestSafeS3FilesReader:
    async def test_ok_read(self, faker: faker.Faker) -> None:
        file_content: typing.Final = generate_binary_content(faker)
        bucket_name, s3_key = faker.pystr(), faker.pystr()
        s3_client_mock: typing.Final = mock.Mock(
            get_object=mock.AsyncMock(return_value={"Body": mock.Mock(read=mock.AsyncMock(return_value=file_content))})
        )

        read_file: typing.Final = await SafeS3FilesService(
            s3_client=s3_client_mock, file_validator=mock.Mock()
        ).read_file(s3_path=f"{bucket_name}/{s3_key}")

        s3_client_mock.get_object.assert_called_once_with(Bucket=bucket_name, Key=s3_key)
        assert read_file == file_content

    async def test_ok_stream(self, faker: faker.Faker) -> None:
        file_content_chunks: typing.Final = [
            generate_binary_content(faker) for _ in range(faker.pyint(min_value=2, max_value=10))
        ]
        bucket_name, s3_key = faker.pystr(), faker.pystr()
        s3_client_mock: typing.Final = mock.Mock(
            get_object=mock.AsyncMock(
                return_value={"Body": mock.Mock(read=mock.AsyncMock(side_effect=[*file_content_chunks, ""]))}
            )
        )

        read_chunks: typing.Final = [
            one_chunk
            async for one_chunk in SafeS3FilesService(s3_client=s3_client_mock, file_validator=mock.Mock()).stream_file(
                s3_path=f"{bucket_name}/{s3_key}"
            )
        ]

        s3_client_mock.get_object.assert_called_once_with(Bucket=bucket_name, Key=s3_key)
        assert read_chunks == file_content_chunks

    async def test_fails_to_parse_s3_path(self, faker: faker.Faker) -> None:
        with pytest.raises(InvalidS3PathError):
            await SafeS3FilesService(s3_client=mock.Mock(), file_validator=mock.Mock()).read_file(s3_path=faker.pystr())
