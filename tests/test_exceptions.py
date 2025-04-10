import typing

import faker

from safe_s3_storage.exceptions import ThreatDetectedError
from tests.conftest import generate_binary_content


def test_exception_str(faker: faker.Faker) -> None:
    antivirus_response: typing.Final = generate_binary_content(faker)
    assert str(ThreatDetectedError(antivirus_response=antivirus_response)) == f"({antivirus_response=})"
