"""force row level security on users so table owner is subject to RLS

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.execute("ALTER TABLE users NO FORCE ROW LEVEL SECURITY")
