import dataclasses


@dataclasses.dataclass
class BaseError(Exception):
    def __str__(self) -> str:
        return self.__repr__().replace(self.__class__.__name__, "")


@dataclasses.dataclass
class KasperskyScanEngineThreatDetectedError(BaseError):
    response: bytes
    file_name: str


@dataclasses.dataclass
class NotAllowedMimeTypeError(BaseError):
    file_name: str
    mime_type: str
    allowed_mime_types: list[str]


@dataclasses.dataclass
class TooLargeFileError(BaseError):
    file_name: str
    file_size: int
    mime_type: str
    max_size: int


@dataclasses.dataclass
class FailedToConvertImageError(BaseError):
    file_name: str
    mime_type: str


@dataclasses.dataclass
class InvalidS3PathError(BaseError):
    s3_path: str


@dataclasses.dataclass
class FailedToReplaceS3BaseUrlWithProxyBaseUrlError(BaseError):
    s3_file_presigned_url: str
    proxy_base_url: str
