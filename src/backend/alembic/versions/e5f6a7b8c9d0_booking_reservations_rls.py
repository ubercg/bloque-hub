"""booking: reservations table with RLS

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

reservationstatus_enum = postgresql.ENUM(
    "PENDING_SLIP",
    "AWAITING_PAYMENT",
    "PAYMENT_UNDER_REVIEW",
    "CONFIRMED",
    "EXPIRED",
    name="reservationstatus",
    create_type=False,
)

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE reservationstatus AS ENUM ("
        "'PENDING_SLIP', 'AWAITING_PAYMENT', 'PAYMENT_UNDER_REVIEW', 'CONFIRMED', 'EXPIRED'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("status", reservationstatus_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reservations_tenant_id"), "reservations", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_reservations_user_id"), "reservations", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_reservations_status"), "reservations", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_reservations_space_fecha"),
        "reservations",
        ["space_id", "fecha"],
        unique=False,
    )

    op.execute("ALTER TABLE reservations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON reservations
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_insert ON reservations
        FOR INSERT
        WITH CHECK (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_update ON reservations
        FOR UPDATE
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation_delete ON reservations
        FOR DELETE
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute("ALTER TABLE reservations FORCE ROW LEVEL SECURITY")

    op.create_foreign_key(
        "fk_inventory_reservation_id",
        "inventory",
        "reservations",
        ["reservation_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inventory_reservation_id", "inventory", type_="foreignkey"
    )

    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON reservations")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON reservations")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON reservations")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON reservations")
    op.execute("ALTER TABLE reservations DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_reservations_space_fecha"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_status"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_user_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_tenant_id"), table_name="reservations")
    op.drop_table("reservations")

    op.execute("DROP TYPE reservationstatus")
