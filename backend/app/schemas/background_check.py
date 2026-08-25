import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NameProposalResponse(BaseModel):
    firstName: str
    lastName: str
    dateOfBirth: date


class BackgroundCheckCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    firstName: str = Field(min_length=1, max_length=100)
    lastName: str = Field(min_length=1, max_length=100)
    dateOfBirth: date

    @field_validator("firstName", "lastName")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("dateOfBirth")
    @classmethod
    def validate_birth_date(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("dateOfBirth must be in the past")
        return value


class BackgroundCheckCreatedResponse(BaseModel):
    id: uuid.UUID
    checkId: str
    employeeId: str
    firstName: str
    lastName: str
    dateOfBirth: date
    requestedBy: uuid.UUID
    requestedAt: datetime
    status: Literal["pending", "clear", "flagged"]


class BackgroundCheckHistoryItem(BaseModel):
    checkId: str
    status: Literal["pending", "clear", "flagged"]
    createdAt: datetime | None = None
    completedAt: datetime | None = None
    localRequestId: uuid.UUID | None = None
    requestedBy: uuid.UUID | None = None
    requestedByName: str | None = None
    requestedFirstName: str | None = None
    requestedLastName: str | None = None


class BackgroundCheckHistoryResponse(BaseModel):
    employeeId: str
    checks: list[BackgroundCheckHistoryItem]


class BackgroundCheckDetailResponse(BaseModel):
    checkId: str
    employeeId: str
    firstName: str | None = None
    lastName: str | None = None
    dateOfBirth: date | None = None
    status: Literal["pending", "clear", "flagged"]
    criminalRecord: bool | None = None
    educationVerified: bool | None = None
    employmentVerified: bool | None = None
    creditScore: Literal["excellent", "good", "fair", "poor"] | None = None
    createdAt: datetime | None = None
    completedAt: datetime | None = None
