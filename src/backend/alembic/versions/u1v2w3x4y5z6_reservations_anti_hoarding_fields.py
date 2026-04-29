"""reservations: created_from_ip, device_fingerprint for anti-hoarding and audit

Revision ID: u1v2w3x4y5z6
Revises: t0u1v2w3x4y5
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, None] = "t0u1v2w3x4y5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column("created_from_ip", sa.String(45), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column("device_fingerprint", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reservations", "device_fingerprint")
    op.drop_column("reservations", "created_from_ip")
