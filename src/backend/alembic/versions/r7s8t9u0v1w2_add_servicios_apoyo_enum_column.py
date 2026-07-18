"""quote_wizard_details.servicios_apoyo — fixed enum list (REQ-012 §4.5, PR#8)

servicios_apoyo was originally modeled via QuoteAdditionalService (a catalog
UUID lookup), which is wrong for this REQ: §4.5 defines it as a FIXED closed
multi-enum of 8 labels, not dynamic catalog items, and there is no public
catalog-listing endpoint for the wizard to use. This migration adds a plain
`text[]` column on `quote_wizard_details` to hold the selected enum values
verbatim (validated by the Pydantic `ServicioApoyo` enum at the API layer).
Not priced — consistent with `Quote.total = spaces only`.

Revision ID: r7s8t9u0v1w2
Revises: q1r2s3t4u5v6
Create Date: 2026-07-18

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "r7s8t9u0v1w2"
down_revision: Union[str, None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "quote_wizard_details",
        sa.Column(
            "servicios_apoyo",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("quote_wizard_details", "servicios_apoyo")
