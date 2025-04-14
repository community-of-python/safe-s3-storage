import dataclasses

from safe_s3_storage.s3_read import SafeS3FilesReader
from safe_s3_storage.s3_upload import SafeS3FilesUploader


@dataclasses.dataclass(kw_only=True, frozen=True)
class SafeS3FilesService(SafeS3FilesReader, SafeS3FilesUploader): ...
