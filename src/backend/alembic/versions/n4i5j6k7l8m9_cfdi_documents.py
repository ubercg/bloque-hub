"""cfdi_documents table + RLS (FR-36)

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "n4i5j6k7l8m9"
down_revision: Union[str, None] = "m3h4i5j6k7l8"
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
    op.create_table(
        "cfdi_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False, server_default="INGRESO"),
        sa.Column("uuid_fiscal", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rfc_emisor", sa.String(length=20), nullable=False),
        sa.Column("rfc_receptor", sa.String(length=20), nullable=False),
        sa.Column("razon_social_receptor", sa.String(length=200), nullable=True),
        sa.Column("regimen_receptor", sa.String(length=10), nullable=True),
        sa.Column("uso_cfdi", sa.String(length=5), nullable=False, server_default="G03"),
        sa.Column("forma_pago", sa.String(length=5), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("iva_monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("xml_url", sa.Text(), nullable=True),
        sa.Column("pdf_url", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False, server_default="PENDIENTE"),
        sa.Column("timbrado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duracion_timbrado_ms", sa.Integer(), nullable=True),
        sa.Column("cancelado_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_codigo", sa.String(length=20), nullable=True),
        sa.Column("error_descripcion", sa.Text(), nullable=True),
        sa.Column("intentos_timbrado", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ultimo_intento_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cfdi_documents_tenant_id", "cfdi_documents", ["tenant_id"], unique=False)
    op.create_index("ix_cfdi_documents_reservation_id", "cfdi_documents", ["reservation_id"], unique=False)
    op.create_index("ix_cfdi_documents_estado", "cfdi_documents", ["estado"], unique=False)
    op.create_index("ix_cfdi_documents_uuid_fiscal", "cfdi_documents", ["uuid_fiscal"], unique=True,
                    postgresql_where=sa.text("uuid_fiscal IS NOT NULL"))
    _rls("cfdi_documents")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON cfdi_documents")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON cfdi_documents")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON cfdi_documents")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON cfdi_documents")
    op.execute("ALTER TABLE cfdi_documents DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_cfdi_documents_uuid_fiscal", table_name="cfdi_documents")
    op.drop_index("ix_cfdi_documents_estado", table_name="cfdi_documents")
    op.drop_index("ix_cfdi_documents_reservation_id", table_name="cfdi_documents")
    op.drop_index("ix_cfdi_documents_tenant_id", table_name="cfdi_documents")
    op.drop_table("cfdi_documents")
