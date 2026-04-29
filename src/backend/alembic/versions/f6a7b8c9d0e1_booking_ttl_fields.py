"""booking: add ttl_expires_at and ttl_frozen to reservations

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column("ttl_frozen", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("reservations", "ttl_frozen")
    op.drop_column("reservations", "ttl_expires_at")
