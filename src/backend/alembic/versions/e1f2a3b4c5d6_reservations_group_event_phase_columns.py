"""reservations: group_event_id, multi_day, phase, ready_blocked + SOFT_HOLD

Alinea la BD con `app.modules.booking.models.Reservation` (FR-05 / eventos agrupados).

Revision ID: e1f2a3b4c5d6
Revises: c8d9e0f1a2b3
Create Date: 2026-03-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE eventphase AS ENUM ('USO', 'MONTAJE', 'DESMONTAJE');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )
    op.execute("ALTER TYPE reservationstatus ADD VALUE IF NOT EXISTS 'SOFT_HOLD'")

    op.add_column(
        "reservations",
        sa.Column("group_event_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "multi_day",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "phase",
            sa.Enum(
                "USO",
                "MONTAJE",
                "DESMONTAJE",
                name="eventphase",
                create_type=False,
            ),
            nullable=False,
            server_default="USO",
        ),
    )
    op.add_column(
        "reservations",
        sa.Column(
            "ready_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index(
        op.f("ix_reservations_group_event_id"),
        "reservations",
        ["group_event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_reservations_group_event_id"), table_name="reservations")
    op.drop_column("reservations", "ready_blocked")
    op.drop_column("reservations", "phase")
    op.drop_column("reservations", "multi_day")
    op.drop_column("reservations", "group_event_id")
    op.execute("DROP TYPE IF EXISTS eventphase")
