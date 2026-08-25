import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models import EmployeeRole, EmployeeStatus


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class EmployeeAuthResponse(BaseModel):
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


class CsrfTokenResponse(BaseModel):
    csrf_token: str
