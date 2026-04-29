"""spaces: piso, descripcion, matterport_url, amenidades for catalog

Revision ID: s9n0o1p2q3r4
Revises: r8m9n0o1p2q3
Create Date: 2026-02-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "s9n0o1p2q3r4"
down_revision: Union[str, None] = "r8m9n0o1p2q3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("spaces", sa.Column("piso", sa.Integer(), nullable=True))
    op.add_column("spaces", sa.Column("descripcion", sa.Text(), nullable=True))
    op.add_column("spaces", sa.Column("matterport_url", sa.String(length=2048), nullable=True))
    op.add_column("spaces", sa.Column("amenidades", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("spaces", "amenidades")
    op.drop_column("spaces", "matterport_url")
    op.drop_column("spaces", "descripcion")
    op.drop_column("spaces", "piso")
