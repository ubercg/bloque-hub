"""inventory: add SOFT_HOLD to slotstatus and quote_id column

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "g7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE slotstatus ADD VALUE IF NOT EXISTS 'SOFT_HOLD'")
    op.add_column(
        "inventory",
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inventory", "quote_id")
    # PostgreSQL does not support removing an enum value easily; leave SOFT_HOLD in type
    # or recreate enum and column if strict downgrade is required
