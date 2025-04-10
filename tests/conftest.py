import pytest
import stamina


@pytest.fixture(scope="session", autouse=True)
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session", autouse=True)
def deactivate_retries() -> None:
    stamina.set_active(False)
