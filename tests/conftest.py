import typing

import faker
import pytest


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> str:
    return "asyncio"


JS_MIME_TYPE: typing.Final = "text/javascript"


def generate_binary_content(faker: faker.Faker) -> bytes:
    return faker.binary(length=faker.pyint(min_value=10, max_value=100))
