import base64
import dataclasses
import enum
import typing

import httpx
import pydantic
import stamina

from safe_s3_storage.exceptions import KasperskyScanEngineThreatDetectedError


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


@dataclasses.dataclass(kw_only=True, slots=True, frozen=True)
class KasperskyScanEngineClient:
    httpx_client: httpx.AsyncClient
    service_url: str
    client_name: str
    timeout_ms: int = 10000
    max_retries: int = 3

    async def _send_scan_memory_request(self, payload: dict[str, typing.Any]) -> bytes:
        response: typing.Final = await self.httpx_client.post(url=self.service_url, json=payload)
        response.raise_for_status()
        return response.content

    async def scan_memory(self, *, file_name: str, file_content: bytes) -> None:
        payload: typing.Final = KasperskyScanEngineRequest(
            timeout=str(self.timeout_ms), object=base64.b64encode(file_content).decode(), name=self.client_name
        ).model_dump(mode="json")
        response: typing.Final = await stamina.retry(on=httpx.HTTPError, attempts=self.max_retries)(
            self._send_scan_memory_request
        )(payload)
        validated_response: typing.Final = KasperskyScanEngineResponse.model_validate_json(response)
        if validated_response.scanResult == KasperskyScanEngineScanResult.DETECT:
            raise KasperskyScanEngineThreatDetectedError(response=response, file_name=file_name)
