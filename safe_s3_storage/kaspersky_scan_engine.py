import base64
import dataclasses
import enum
import typing

import httpx2
import pydantic

from safe_s3_storage.exceptions import (
    KasperskyScanEngineConnectionStatusError,
    KasperskyScanEngineInvalidResponseError,
    KasperskyScanEngineThreatDetectedError,
)


class KasperskyScanEngineRequest(pydantic.BaseModel):
    timeout: str
    object: str
    name: str


# https://support.kaspersky.ru/scan-engine/2.1/193001
class KasperskyScanEngineScanResult(str, enum.Enum):
    CLEAN = "CLEAN"
    DETECT = "DETECT"
    DISINFECTED = "DISINFECTED"
    DELETED = "DELETED"
    NON_SCANNED = "NON_SCANNED"
    SERVER_ERROR = "SERVER_ERROR"


class KasperskyScanEngineResponse(pydantic.BaseModel):
    scanResult: KasperskyScanEngineScanResult  # noqa: N815

    @pydantic.field_validator("scanResult", mode="before")
    @classmethod
    def _strip_v3_0_reason(cls, scan_result: object) -> object:
        return scan_result.split(" (", 1)[0] if isinstance(scan_result, str) else scan_result


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class KasperskyScanEngineClient:
    httpx_client: httpx2.AsyncClient
    service_url: str
    client_name: str
    timeout_ms: int = 10000
    max_retries: int = 3

    async def _send_scan_memory_request(self, payload: dict[str, typing.Any]) -> bytes:
        retries_left = self.max_retries
        while True:
            try:
                response = await self.httpx_client.post(url=self.service_url, json=payload)
                response.raise_for_status()
            except (httpx2.HTTPStatusError, httpx2.TransportError) as exc:  # noqa: PERF203
                is_retryable = isinstance(exc, httpx2.TransportError) or exc.response.is_server_error
                if not is_retryable or retries_left <= 0:
                    raise
                retries_left -= 1
            else:
                return response.content

    async def scan_memory(self, *, file_name: str, file_content: bytes) -> None:
        payload: typing.Final = KasperskyScanEngineRequest(
            timeout=str(self.timeout_ms), object=base64.b64encode(file_content).decode(), name=self.client_name
        ).model_dump(mode="json")
        try:
            response: typing.Final = await self._send_scan_memory_request(payload)
        except (httpx2.HTTPStatusError, httpx2.TransportError) as exc:
            raise KasperskyScanEngineConnectionStatusError from exc
        try:
            validated_response: typing.Final = KasperskyScanEngineResponse.model_validate_json(response)
        except pydantic.ValidationError as exc:
            raise KasperskyScanEngineInvalidResponseError(response=response, file_name=file_name) from exc
        if validated_response.scanResult == KasperskyScanEngineScanResult.DETECT:
            raise KasperskyScanEngineThreatDetectedError(response=response, file_name=file_name)
