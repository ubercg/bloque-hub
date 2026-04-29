"""tenants: max_discount_threshold (align ORM with DB)

Revision ID: c8d9e0f1a2b3
Revises: 5b2da7c0de33
Create Date: 2026-03-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "5b2da7c0de33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Modelo Tenant incluye max_discount_threshold; migración faltante en cadena previa.
    op.execute(
        """
        ALTER TABLE tenants
        ADD COLUMN IF NOT EXISTS max_discount_threshold NUMERIC(5, 2) NOT NULL DEFAULT 0
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS max_discount_threshold")
