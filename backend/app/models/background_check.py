from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class BackgroundCheckStatus(str, enum.Enum):
    PENDING = "pending"
    CLEAR = "clear"
    FLAGGED = "flagged"


class BackgroundCheckRequest(Base):
    __tablename__ = "background_check_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    external_check_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    employee_number_snapshot: Mapped[str] = mapped_column(String(30), nullable=False)
    first_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth_snapshot: Mapped[date] = mapped_column(Date, nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    initial_status: Mapped[BackgroundCheckStatus] = mapped_column(
        Enum(
            BackgroundCheckStatus,
            name="background_check_status",
            values_callable=lambda enum_type: [item.value for item in enum_type],
        ),
        nullable=False,
    )
    last_status: Mapped[BackgroundCheckStatus] = mapped_column(
        Enum(
            BackgroundCheckStatus,
            name="background_check_status",
            values_callable=lambda enum_type: [item.value for item in enum_type],
            create_type=False,
        ),
        nullable=False,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    employee: Mapped[Employee] = relationship(foreign_keys=[employee_id])
    requester: Mapped[Employee] = relationship(foreign_keys=[requested_by])


from app.models.employee import Employee  # noqa: E402
