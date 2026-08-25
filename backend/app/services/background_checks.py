from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings


BackgroundStatus = Literal["pending", "clear", "flagged"]


class ExternalBackgroundCheckCreated(BaseModel):
    checkId: str
    employeeId: str
    status: BackgroundStatus
    createdAt: str
    message: str | None = None


class ExternalBackgroundCheckResult(BaseModel):
    checkId: str
    employeeId: str
    firstName: str | None = None
    lastName: str | None = None
    dateOfBirth: date | None = None
    status: BackgroundStatus
    criminalRecord: bool | None = None
    educationVerified: bool | None = None
    employmentVerified: bool | None = None
    creditScore: Literal["excellent", "good", "fair", "poor"] | None = None
    createdAt: datetime | None = None
    completedAt: datetime | None = None


class ExternalBackgroundCheckSummary(BaseModel):
    checkId: str
    status: BackgroundStatus
    createdAt: datetime | None = None
    completedAt: datetime | None = None


class ExternalBackgroundCheckList(BaseModel):
    employeeId: str
    checks: list[ExternalBackgroundCheckSummary] = []
    totalCount: int = 0


@dataclass(frozen=True)
class BackgroundCheckProviderError(Exception):
    kind: Literal["bad_request", "not_found", "server_error", "unavailable", "timeout", "invalid_response"]
    retry_after: int | None = None


class BackgroundCheckClient:
    def __init__(self, base_url: str, timeout_seconds: float, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def create(self, *, employee_id: str, first_name: str, last_name: str, date_of_birth: str) -> ExternalBackgroundCheckCreated:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds, transport=self.transport) as client:
                response = await client.post("/background-checks", json={"employeeId": employee_id, "firstName": first_name, "lastName": last_name, "dateOfBirth": date_of_birth})
        except httpx.TimeoutException as exc:
            raise BackgroundCheckProviderError("timeout") from exc
        except httpx.RequestError as exc:
            raise BackgroundCheckProviderError("unavailable") from exc

        if response.status_code == 400:
            raise BackgroundCheckProviderError("bad_request")
        if response.status_code == 500:
            raise BackgroundCheckProviderError("server_error")
        if response.status_code == 503:
            retry_after = None
            try:
                value = response.json().get("retryAfter")
                retry_after = value if isinstance(value, int) and value >= 0 else None
            except ValueError:
                pass
            raise BackgroundCheckProviderError("unavailable", retry_after)
        if response.status_code != 201:
            raise BackgroundCheckProviderError("invalid_response")
        try:
            return ExternalBackgroundCheckCreated.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise BackgroundCheckProviderError("invalid_response") from exc

    async def get(self, check_id: str) -> ExternalBackgroundCheckResult:
        response = await self._get(f"/background-checks/{check_id}")
        self._raise_for_get_error(response)
        try:
            return ExternalBackgroundCheckResult.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise BackgroundCheckProviderError("invalid_response") from exc

    async def list_for_employee(self, employee_id: str) -> ExternalBackgroundCheckList:
        response = await self._get("/background-checks", params={"employeeId": employee_id})
        self._raise_for_get_error(response)
        try:
            return ExternalBackgroundCheckList.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise BackgroundCheckProviderError("invalid_response") from exc

    async def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds, transport=self.transport) as client:
                return await client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise BackgroundCheckProviderError("timeout") from exc
        except httpx.RequestError as exc:
            raise BackgroundCheckProviderError("unavailable") from exc

    @staticmethod
    def _raise_for_get_error(response: httpx.Response) -> None:
        if response.status_code == 200:
            return
        if response.status_code == 400:
            raise BackgroundCheckProviderError("bad_request")
        if response.status_code == 404:
            raise BackgroundCheckProviderError("not_found")
        if response.status_code == 500:
            raise BackgroundCheckProviderError("server_error")
        if response.status_code == 503:
            retry_after = None
            try:
                value = response.json().get("retryAfter")
                retry_after = value if isinstance(value, int) and value >= 0 else None
            except ValueError:
                pass
            raise BackgroundCheckProviderError("unavailable", retry_after)
        raise BackgroundCheckProviderError("invalid_response")


def get_background_check_client() -> BackgroundCheckClient:
    settings = get_settings()
    return BackgroundCheckClient(settings.background_check_api_url, settings.background_check_timeout_seconds)
