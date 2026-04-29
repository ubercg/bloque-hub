"""Add contract_snapshot_hash to contracts (CFDI snapshot).

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, None] = "g2h3i4j5k6l7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "contracts",
        sa.Column("contract_snapshot_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("contracts", "contract_snapshot_hash")
