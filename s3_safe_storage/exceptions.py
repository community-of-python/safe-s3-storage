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
