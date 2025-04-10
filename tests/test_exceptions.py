import faker

from s3_safe_storage.exceptions import ThreatDetectedError
from tests.conftest import generate_binary_content


def test_exception_str(faker: faker.Faker) -> None:
    antivirus_response = generate_binary_content(faker)
    assert str(ThreatDetectedError(antivirus_response=antivirus_response)) == f"({antivirus_response=})"
