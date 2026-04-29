"""Add COMPLETED to reservationstatus enum.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
Create Date: 2026-03-06

"""
from typing import Sequence, Union

from alembic import op

revision: str = "y5z6a7b8c9d0"
down_revision: Union[str, None] = "x4y5z6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE reservationstatus ADD VALUE IF NOT EXISTS 'COMPLETED'")


def downgrade() -> None:
    # PostgreSQL does not support removing an enum value easily; would require recreating the type.
    # Leave COMPLETED in place; no-op.
    pass
