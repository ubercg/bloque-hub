"""access: access_qr_tokens for gate validation

Revision ID: t0u1v2w3x4y5
Revises: s9n0o1p2q3r4
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, None] = "s9n0o1p2q3r4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "access_qr_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_qr", sa.String(64), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scanned_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scanned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_access_qr_tokens_token_qr", "access_qr_tokens", ["token_qr"], unique=True)
    op.create_index("ix_access_qr_tokens_reservation_id", "access_qr_tokens", ["reservation_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_access_qr_tokens_reservation_id", table_name="access_qr_tokens")
    op.drop_index("ix_access_qr_tokens_token_qr", table_name="access_qr_tokens")
    op.drop_table("access_qr_tokens")
