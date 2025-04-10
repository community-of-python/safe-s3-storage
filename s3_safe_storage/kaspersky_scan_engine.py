import base64
import dataclasses
import enum
import typing

import httpx
import pydantic
import stamina

from s3_safe_storage.exceptions import ThreatDetectedError


class KasperskyScanEngineRequest(pydantic.BaseModel):
    timeout: str
    object: str


# https://support.kaspersky.ru/scan-engine/2.1/193001
class KasperskyScanEngineScanResult(enum.StrEnum):
    CLEAN = enum.auto()
    DETECT = enum.auto()
    DISINFECTED = enum.auto()
    DELETED = enum.auto()
    NON_SCANNED = enum.auto()
    SERVER_ERROR = enum.auto()


class KasperskyScanEngineResponse(pydantic.BaseModel):
    scanResult: KasperskyScanEngineScanResult  # noqa: N815


@dataclasses.dataclass(kw_only=True, frozen=True, slots=True)
class KasperskyScanEngineClient:
    httpx_client: httpx.AsyncClient

    kaspersky_scan_engine_url: str = "http://127.0.0.1:9998/api/v3.0/scanmemory"
    kaspersky_scan_engine_timeout_ms: int = 10000
    kaspersky_scan_engine_retries: int = 3

    async def _send_scan_memory_request(self, payload: dict[str, typing.Any]) -> bytes:
        response = await self.httpx_client.post(url=self.kaspersky_scan_engine_url, json=payload)
        response.raise_for_status()
        return response.content

    async def scan_memory(self, file_content: bytes) -> None:
        payload = KasperskyScanEngineRequest(
            timeout=str(self.kaspersky_scan_engine_timeout_ms), object=base64.b64encode(file_content).decode()
        ).model_dump(mode="json")
        response: typing.Final = await stamina.retry(on=httpx.HTTPError, attempts=self.kaspersky_scan_engine_retries)(
            self._send_scan_memory_request
        )(payload)
        validated_response = KasperskyScanEngineResponse.model_validate_json(response)
        if validated_response.scanResult == KasperskyScanEngineScanResult.DETECT:
            raise ThreatDetectedError(antivirus_response=response)
