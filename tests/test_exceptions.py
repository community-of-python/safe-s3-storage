import typing

import faker

from safe_s3_storage.exceptions import KasperskyScanEngineThreatDetectedError
from tests.conftest import generate_binary_content


def test_exception_str(faker: faker.Faker) -> None:
    antivirus_response: typing.Final = generate_binary_content(faker)
    file_name: typing.Final = faker.file_name()
    assert (
        str(KasperskyScanEngineThreatDetectedError(response=antivirus_response, file_name=file_name))
        == f"({antivirus_response=}, {file_name=})"
    )
