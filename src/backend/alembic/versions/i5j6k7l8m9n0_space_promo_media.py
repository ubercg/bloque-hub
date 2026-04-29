"""spaces: promo_hero_url y promo_gallery_urls (catálogo / promoción FE).

Revision ID: i5j6k7l8m9n0
Revises: h3i4j5k6l7m8
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "i5j6k7l8m9n0"
down_revision: Union[str, None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "spaces",
        sa.Column("promo_hero_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "spaces",
        sa.Column(
            "promo_gallery_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("spaces", "promo_gallery_urls")
    op.drop_column("spaces", "promo_hero_url")
