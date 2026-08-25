"""Create background check request tracking.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-25
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_check_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("employee_id", sa.Uuid(), nullable=False),
        sa.Column("external_check_id", sa.String(length=200), nullable=False),
        sa.Column("employee_number_snapshot", sa.String(length=30), nullable=False),
        sa.Column("first_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("last_name_snapshot", sa.String(length=100), nullable=False),
        sa.Column("date_of_birth_snapshot", sa.Date(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column(
            "initial_status",
            sa.Enum("pending", "clear", "flagged", name="background_check_status"),
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["requested_by"], ["employees.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_check_id"),
    )
    op.create_index(op.f("ix_background_check_requests_employee_id"), "background_check_requests", ["employee_id"])
    op.create_index(op.f("ix_background_check_requests_requested_by"), "background_check_requests", ["requested_by"])


def downgrade() -> None:
    op.drop_index(op.f("ix_background_check_requests_requested_by"), table_name="background_check_requests")
    op.drop_index(op.f("ix_background_check_requests_employee_id"), table_name="background_check_requests")
    op.drop_table("background_check_requests")
    sa.Enum(name="background_check_status").drop(op.get_bind(), checkfirst=True)
