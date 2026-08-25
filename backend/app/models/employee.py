from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, TimestampMixin


class EmployeeRole(str, enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    ADMIN = "ADMIN"


class EmployeeStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    TERMINATED = "TERMINATED"


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_employees_email_lowercase"),
        CheckConstraint(
            "(status = 'TERMINATED' AND terminated_at IS NOT NULL) "
            "OR (status = 'ACTIVE' AND terminated_at IS NULL)",
            name="ck_employees_termination_state",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(String(500))
    role: Mapped[EmployeeRole] = mapped_column(
        Enum(EmployeeRole, name="employee_role"),
        default=EmployeeRole.EMPLOYEE,
        server_default=EmployeeRole.EMPLOYEE.value,
        nullable=False,
    )
    status: Mapped[EmployeeStatus] = mapped_column(
        Enum(EmployeeStatus, name="employee_status"),
        default=EmployeeStatus.ACTIVE,
        server_default=EmployeeStatus.ACTIVE.value,
        nullable=False,
    )
    terminated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminated_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL")
    )
    terminator: Mapped[Employee | None] = relationship(
        remote_side="Employee.id", foreign_keys=[terminated_by]
    )
    sessions: Mapped[list[AuthSession]] = relationship(
        back_populates="employee", cascade="all, delete-orphan"
    )

    @validates("email")
    def normalize_email(self, _: str, value: str) -> str:
        return value.strip().lower()


from app.models.session import AuthSession  # noqa: E402
