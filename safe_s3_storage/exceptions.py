import dataclasses


@dataclasses.dataclass
class BaseS3SafeStorageError(Exception):
    def __str__(self) -> str:
        return self.__repr__().replace(self.__class__.__name__, "")


@dataclasses.dataclass
class ThreatDetectedError(BaseS3SafeStorageError):
    antivirus_response: bytes


@dataclasses.dataclass
class UnsupportedMimeTypeError(BaseS3SafeStorageError):
    file_name: str
    mime_type: str
    allowed_mime_types: list[str]


@dataclasses.dataclass
class TooLargeFileError(BaseS3SafeStorageError):
    file_name: str
    mime_type: str
    max_size: int


@dataclasses.dataclass
class FailedToConvertImageError(BaseS3SafeStorageError):
    file_name: str
    mime_type: str
