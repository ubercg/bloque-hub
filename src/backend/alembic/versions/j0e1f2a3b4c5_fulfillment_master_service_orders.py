"""fulfillment: master_service_orders, checklists, service_order_items with RLS on OS

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

masterserviceorderstatus_enum = postgresql.ENUM(
    "PENDING",
    "IN_PROGRESS",
    "READY",
    "CANCELLED",
    name="masterserviceorderstatus",
    create_type=False,
)
serviceorderitemstatus_enum = postgresql.ENUM(
    "PENDING",
    "COMPLETED",
    name="serviceorderitemstatus",
    create_type=False,
)

revision: str = "j0e1f2a3b4c5"
down_revision: Union[str, None] = "i9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_insert ON {table}
        FOR INSERT
        WITH CHECK (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_update ON {table}
        FOR UPDATE
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_delete ON {table}
        FOR DELETE
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE masterserviceorderstatus AS ENUM ("
        "'PENDING', 'IN_PROGRESS', 'READY', 'CANCELLED'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE serviceorderitemstatus AS ENUM ("
        "'PENDING', 'COMPLETED'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "master_service_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", masterserviceorderstatus_enum, nullable=False),
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
        sa.CheckConstraint(
            "reservation_id IS NOT NULL OR contract_id IS NOT NULL",
            name="chk_os_reservation_or_contract",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_master_service_orders_tenant_id"),
        "master_service_orders",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_master_service_orders_reservation_id"),
        "master_service_orders",
        ["reservation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_master_service_orders_contract_id"),
        "master_service_orders",
        ["contract_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_master_service_orders_status"),
        "master_service_orders",
        ["status"],
        unique=False,
    )

    op.create_table(
        "checklists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("master_service_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["master_service_order_id"],
            ["master_service_orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_checklists_master_service_order_id"),
        "checklists",
        ["master_service_order_id"],
        unique=False,
    )

    op.create_table(
        "service_order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("checklist_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", serviceorderitemstatus_enum, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["checklist_id"],
            ["checklists.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_service_order_items_checklist_id"),
        "service_order_items",
        ["checklist_id"],
        unique=False,
    )

    _rls("master_service_orders")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON master_service_orders")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON master_service_orders")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON master_service_orders")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON master_service_orders")
    op.execute("ALTER TABLE master_service_orders DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        op.f("ix_service_order_items_checklist_id"),
        table_name="service_order_items",
    )
    op.drop_table("service_order_items")

    op.drop_index(
        op.f("ix_checklists_master_service_order_id"),
        table_name="checklists",
    )
    op.drop_table("checklists")

    op.drop_index(
        op.f("ix_master_service_orders_status"),
        table_name="master_service_orders",
    )
    op.drop_index(
        op.f("ix_master_service_orders_contract_id"),
        table_name="master_service_orders",
    )
    op.drop_index(
        op.f("ix_master_service_orders_reservation_id"),
        table_name="master_service_orders",
    )
    op.drop_index(
        op.f("ix_master_service_orders_tenant_id"),
        table_name="master_service_orders",
    )
    op.drop_table("master_service_orders")

    op.execute("DROP TYPE serviceorderitemstatus")
    op.execute("DROP TYPE masterserviceorderstatus")
