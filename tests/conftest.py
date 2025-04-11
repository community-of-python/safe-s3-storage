import typing

import faker
import pytest
import stamina


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def deactivate_retries() -> None:
    stamina.set_active(False)


MIME_OCTET_STREAM: typing.Final = "application/octet-stream"


def generate_binary_content(faker: faker.Faker) -> bytes:
    return faker.binary(length=faker.pyint(min_value=10, max_value=100))
