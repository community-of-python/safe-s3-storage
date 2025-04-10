import dataclasses


@dataclasses.dataclass
class BaseError(Exception):
    def __str__(self) -> str:
        return self.__repr__().replace(self.__class__.__name__, "")


@dataclasses.dataclass
class ThreatDetectedError(BaseError):
    antivirus_response: bytes
    file_name: str


@dataclasses.dataclass
class UnsupportedContentTypeError(BaseError):
    file_name: str
    mime_type: str
    allowed_mime_types: list[str]


@dataclasses.dataclass
class TooLargeFileError(BaseError):
    file_name: str
    content_type: str
    max_size: int


@dataclasses.dataclass
class FailedToConvertImageError(BaseError):
    file_name: str
    content_type: str
