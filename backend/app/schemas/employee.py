import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models import EmployeeRole, EmployeeStatus


class EmployeeSelfResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_number: str
    full_name: str
    date_of_birth: date
    email: str
    phone: str | None
    address: str | None
    role: EmployeeRole
    status: EmployeeStatus


class EmployeeSelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str | None = Field(default=None, max_length=30)
    address: str | None = Field(default=None, max_length=500)
