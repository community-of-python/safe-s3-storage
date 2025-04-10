from s3_safe_storage.exceptions import BaseS3SafeStorageError


def test_exception_str() -> None:
    assert str(BaseS3SafeStorageError()) == "()"
