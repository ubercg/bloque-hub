"""inventory: spaces, space_relationships, inventory with RLS

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Use existing enum types (created by DO $$ ... EXCEPTION below)
bookingmode_enum = postgresql.ENUM(
    "SEMI_DIRECT", "QUOTE_REQUIRED", name="bookingmode", create_type=False
)
relationshiptype_enum = postgresql.ENUM(
    "PARENT_CHILD", name="relationshiptype", create_type=False
)
slotstatus_enum = postgresql.ENUM(
    "AVAILABLE",
    "BLOCKED_BY_PARENT",
    "BLOCKED_BY_CHILD",
    "TTL_BLOCKED",
    "RESERVED",
    name="slotstatus",
    create_type=False,
)

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN CREATE TYPE bookingmode AS ENUM ('SEMI_DIRECT', 'QUOTE_REQUIRED'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE relationshiptype AS ENUM ('PARENT_CHILD'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute(
        "DO $$ BEGIN CREATE TYPE slotstatus AS ENUM ("
        "'AVAILABLE', 'BLOCKED_BY_PARENT', 'BLOCKED_BY_CHILD', 'TTL_BLOCKED', 'RESERVED'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "spaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("booking_mode", bookingmode_enum, nullable=False),
        sa.Column("capacidad_maxima", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("layouts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("precio_por_hora", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("ttl_minutos", sa.Integer(), nullable=False, server_default="1440"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_spaces_tenant_slug"),
    )
    op.create_index(op.f("ix_spaces_slug"), "spaces", ["slug"], unique=False)
    op.create_index(op.f("ix_spaces_tenant_id"), "spaces", ["tenant_id"], unique=False)

    op.create_table(
        "space_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("child_space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship_type", relationshiptype_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_space_id", "child_space_id", name="uq_space_relationships_parent_child"
        ),
    )
    op.create_index(
        op.f("ix_space_relationships_tenant_id"),
        "space_relationships",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fin", sa.Time(), nullable=False),
        sa.Column("estado", slotstatus_enum, nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ttl_frozen", sa.Boolean(), nullable=False, server_default="false"),
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
        sa.ForeignKeyConstraint(["space_id"], ["spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "space_id", "fecha", "hora_inicio", "hora_fin", name="uq_inventory_space_slot"
        ),
    )
    op.create_index(
        op.f("ix_inventory_space_id_fecha"),
        "inventory",
        ["space_id", "fecha"],
        unique=False,
    )
    op.create_index(op.f("ix_inventory_tenant_id"), "inventory", ["tenant_id"], unique=False)

    # RLS
    for table in ("spaces", "space_relationships", "inventory"):
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


def downgrade() -> None:
    for table in ("inventory", "space_relationships", "spaces"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_inventory_tenant_id"), table_name="inventory")
    op.drop_index(op.f("ix_inventory_space_id_fecha"), table_name="inventory")
    op.drop_table("inventory")

    op.drop_index(op.f("ix_space_relationships_tenant_id"), table_name="space_relationships")
    op.drop_table("space_relationships")

    op.drop_index(op.f("ix_spaces_tenant_id"), table_name="spaces")
    op.drop_index(op.f("ix_spaces_slug"), table_name="spaces")
    op.drop_table("spaces")

    op.execute("DROP TYPE slotstatus")
    op.execute("DROP TYPE relationshiptype")
    op.execute("DROP TYPE bookingmode")
