"""Create the employees table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-25
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_number", sa.String(length=30), nullable=False),
        sa.Column("full_name", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column(
            "role",
            sa.Enum("EMPLOYEE", "ADMIN", name="employee_role"),
            server_default="EMPLOYEE",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "TERMINATED", name="employee_status"),
            server_default="ACTIVE",
            nullable=False,
        ),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terminated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "email = lower(email)", name="ck_employees_email_lowercase"
        ),
        sa.CheckConstraint(
            "(status = 'TERMINATED' AND terminated_at IS NOT NULL) "
            "OR (status = 'ACTIVE' AND terminated_at IS NULL)",
            name="ck_employees_termination_state",
        ),
        sa.ForeignKeyConstraint(
            ["terminated_by"], ["employees.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("employee_number"),
    )


def downgrade() -> None:
    op.drop_table("employees")
    sa.Enum(name="employee_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="employee_role").drop(op.get_bind(), checkfirst=True)
