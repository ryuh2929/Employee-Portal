"""Add last observed background check state.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-25
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    status_enum = sa.Enum("pending", "clear", "flagged", name="background_check_status", create_type=False)
    op.add_column("background_check_requests", sa.Column("last_status", status_enum, nullable=True))
    op.add_column("background_check_requests", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE background_check_requests SET last_status = initial_status")
    op.alter_column("background_check_requests", "last_status", nullable=False)


def downgrade() -> None:
    op.drop_column("background_check_requests", "last_checked_at")
    op.drop_column("background_check_requests", "last_status")
