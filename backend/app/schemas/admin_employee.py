import re
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import EmployeeRole, EmployeeStatus


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
EMPLOYEE_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9-]+$")


class AdminEmployeeFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_number: str = Field(min_length=1, max_length=30)
    full_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    email: str = Field(min_length=3, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)

    @field_validator("employee_number")
    @classmethod
    def validate_employee_number(cls, value: str) -> str:
        value = value.strip()
        if not EMPLOYEE_NUMBER_PATTERN.fullmatch(value):
            raise ValueError("employee_number may contain only letters, numbers, and hyphens")
        return value

    @field_validator("full_name")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("full_name must not be blank")
        return value

    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("date_of_birth must be in the past")
        return value

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("email must be a valid email address")
        return value


class AdminEmployeeCreate(AdminEmployeeFields):
    initial_password: str


class AdminEmployeeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_number: str | None = Field(default=None, min_length=1, max_length=30)
    full_name: str | None = Field(default=None, min_length=1, max_length=100)
    date_of_birth: date | None = None
    email: str | None = Field(default=None, min_length=3, max_length=320)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)

    _validate_employee_number = field_validator("employee_number")(
        AdminEmployeeFields.validate_employee_number.__func__
    )
    _normalize_full_name = field_validator("full_name")(
        AdminEmployeeFields.normalize_full_name.__func__
    )
    _validate_date_of_birth = field_validator("date_of_birth")(
        AdminEmployeeFields.validate_date_of_birth.__func__
    )
    _normalize_email = field_validator("email")(
        AdminEmployeeFields.normalize_email.__func__
    )


class AdminEmployeeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_number: str
    full_name: str
    email: str
    role: EmployeeRole
    status: EmployeeStatus


class AdminEmployeeDetail(AdminEmployeeListItem):
    date_of_birth: date
    phone: str | None
    address: str | None
    terminated_at: datetime | None
    terminated_by: uuid.UUID | None
