import dataclasses


@dataclasses.dataclass
class ThreatDetectedError(Exception):
    response: bytes


@dataclasses.dataclass
class UnsupportedMimeTypeError(Exception):
    file_name: str
    mime_type: str
    allowed_mime_types: list[str]


@dataclasses.dataclass
class TooLargeFileError(Exception):
    file_name: str
    mime_type: str
    max_size: int


@dataclasses.dataclass
class FailedToConvertImageError(Exception):
    file_name: str
    mime_type: str
@dataclasses.dataclass
class InvalidFilePathError(Exception):
    file_path: str
@dataclasses.dataclass
class S3FileNotFoundError(Exception):
    file_path: str
