import base64
import dataclasses
import enum
import typing

import httpx
import pydantic
import stamina


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
    scan_result: typing.Annotated[KasperskyScanEngineScanResult, pydantic.Field(alias="scanResult")]


@dataclasses.dataclass
class ThreatDetectedError(Exception):
    response: bytes


@dataclasses.dataclass
class KasperskyScanEngineClient:
    kaspersky_scan_engine_url: str
    kaspersky_scan_engine_timeout: int
    http_client: httpx.AsyncClient

    @stamina.retry(on=httpx.HTTPError, attempts=3)
    async def _send_request(self, payload: str) -> bytes:
        response = await self.http_client.post(url=self.kaspersky_scan_engine_url, data=payload)
        response.raise_for_status()
        return response.content

    async def scan_file(self, file_data: bytes) -> None:
        response: typing.Final = await self._send_request(
            KasperskyScanEngineRequest(object=base64.b64encode(file_data).decode()).model_dump_json()
        )
        validated_response = KasperskyScanEngineResponse.model_validate_json(response)
        if validated_response.scan_result == KasperskyScanEngineScanResult.DETECT:
            raise ThreatDetectedError(response=response)
