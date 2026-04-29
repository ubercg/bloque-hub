"""fulfillment: is_critical on service_order_items, evidence_requirements table + RLS

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "k1f2a3b4c5d6"
down_revision: Union[str, None] = "j0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

evidencestatus_enum = postgresql.ENUM(
    "PENDIENTE",
    "PENDIENTE_REVISION",
    "APROBADO",
    "RECHAZADO",
    name="evidencestatus",
    create_type=False,
)


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
    op.add_column(
        "service_order_items",
        sa.Column("is_critical", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.execute(
        "DO $$ BEGIN CREATE TYPE evidencestatus AS ENUM ("
        "'PENDIENTE', 'PENDIENTE_REVISION', 'APROBADO', 'RECHAZADO'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "evidence_requirements",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "master_service_order_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("tipo_documento", sa.String(length=80), nullable=False),
        sa.Column("estado", evidencestatus_enum, nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "plazo_vence_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revisado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_rechazo", sa.Text(), nullable=True),
        sa.Column("intentos_carga", sa.Integer(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(
            ["master_service_order_id"],
            ["master_service_orders.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evidence_requirements_tenant_id"),
        "evidence_requirements",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_requirements_master_service_order_id"),
        "evidence_requirements",
        ["master_service_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evidence_requirements_estado"),
        "evidence_requirements",
        ["estado"],
        unique=False,
    )

    _rls("evidence_requirements")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON evidence_requirements")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON evidence_requirements")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON evidence_requirements")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON evidence_requirements")
    op.execute("ALTER TABLE evidence_requirements DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        op.f("ix_evidence_requirements_estado"),
        table_name="evidence_requirements",
    )
    op.drop_index(
        op.f("ix_evidence_requirements_master_service_order_id"),
        table_name="evidence_requirements",
    )
    op.drop_index(
        op.f("ix_evidence_requirements_tenant_id"),
        table_name="evidence_requirements",
    )
    op.drop_table("evidence_requirements")

    op.execute("DROP TYPE evidencestatus")

    op.drop_column("service_order_items", "is_critical")
