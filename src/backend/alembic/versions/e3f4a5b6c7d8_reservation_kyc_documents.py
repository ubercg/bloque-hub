"""reservation KYC documents + document_type_definitions (FR-25 / expediente borradores)

Revision ID: e3f4a5b6c7d8
Revises: d7e8f9a0b1c2
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls_select_insert_update(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
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
        FOR INSERT WITH CHECK (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY tenant_isolation_update ON {table}
        FOR UPDATE USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )


def _rls_definitions() -> None:
    """Global rows (tenant_id NULL) visible to all tenants; tenant overrides by tenant_id."""
    op.execute("ALTER TABLE document_type_definitions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_type_definitions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY doc_type_definitions_select ON document_type_definitions
        FOR SELECT USING (
            tenant_id IS NULL
            OR tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )
    op.execute(
        """
        CREATE POLICY doc_type_definitions_insert ON document_type_definitions
        FOR INSERT WITH CHECK (
            (tenant_id IS NULL AND current_setting('app.role', true) = 'SUPERADMIN')
            OR (tenant_id::text = current_setting('app.current_tenant_id', true))
        )
        """
    )
    op.execute(
        """
        CREATE POLICY doc_type_definitions_update ON document_type_definitions
        FOR UPDATE USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )


def upgrade() -> None:
    op.create_table(
        "document_type_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "requires_condition",
            sa.String(length=32),
            nullable=False,
            server_default="NONE",
        ),
        sa.Column(
            "mime_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text(
                '\'["application/pdf", "image/jpeg", "image/png", "image/jpg"]\'::jsonb'
            ),
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_type_definitions_tenant_id", "document_type_definitions", ["tenant_id"])
    op.create_index("ix_document_type_definitions_code", "document_type_definitions", ["code"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_document_type_definitions_global_code
        ON document_type_definitions (code)
        WHERE tenant_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_document_type_definitions_tenant_code
        ON document_type_definitions (tenant_id, code)
        WHERE tenant_id IS NOT NULL
        """
    )

    op.create_table(
        "reservation_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("superseded_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_type_id"], ["document_type_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["reservation_documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('ACTIVE', 'SUPERSEDED')", name="ck_reservation_documents_status"),
    )
    op.create_index(
        "ix_reservation_documents_group_event_id",
        "reservation_documents",
        ["group_event_id"],
    )
    op.create_index(
        "ix_reservation_documents_tenant_group_type_status",
        "reservation_documents",
        ["tenant_id", "group_event_id", "document_type_id", "status"],
    )
    op.create_index("ix_reservation_documents_sha256", "reservation_documents", ["sha256"])

    _rls_definitions()
    _rls_select_insert_update("reservation_documents")

    # Seed global types (requires SUPERADMIN for tenant_id NULL)
    op.execute("SELECT set_config('app.role', 'SUPERADMIN', true)")
    op.execute(
        """
        INSERT INTO document_type_definitions (id, tenant_id, code, label, required, requires_condition, mime_rules, active, sort_order)
        VALUES
        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1'::uuid, NULL, 'CONSTANCIA_FISCAL', 'Constancia de situación fiscal', true, 'NONE',
         '["application/pdf","image/jpeg","image/png","image/jpg"]'::jsonb, true, 1),
        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa2'::uuid, NULL, 'INE_FRONT', 'INE — frente', true, 'NONE',
         '["application/pdf","image/jpeg","image/png","image/jpg"]'::jsonb, true, 2),
        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa3'::uuid, NULL, 'INE_BACK', 'INE — reverso', true, 'NONE',
         '["application/pdf","image/jpeg","image/png","image/jpg"]'::jsonb, true, 3),
        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa4'::uuid, NULL, 'DESCUENTO_ACUSE', 'Acuse de solicitud de descuento', true, 'DISCOUNT_CODE',
         '["application/pdf","image/jpeg","image/png","image/jpg"]'::jsonb, true, 4),
        ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa5'::uuid, NULL, 'OTRO', 'Otro documento', false, 'NONE',
         '["application/pdf","image/jpeg","image/png","image/jpg"]'::jsonb, true, 5)
        """
    )


def downgrade() -> None:
    for table, policies in [
        ("reservation_documents", ["tenant_isolation_update", "tenant_isolation_insert", "tenant_isolation"]),
        (
            "document_type_definitions",
            ["doc_type_definitions_update", "doc_type_definitions_insert", "doc_type_definitions_select"],
        ),
    ]:
        for p in policies:
            op.execute(f"DROP POLICY IF EXISTS {p} ON {table}")
    op.execute("ALTER TABLE reservation_documents NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE document_type_definitions NO FORCE ROW LEVEL SECURITY")
    op.drop_table("reservation_documents")
    op.execute("DROP INDEX IF EXISTS uq_document_type_definitions_tenant_code")
    op.execute("DROP INDEX IF EXISTS uq_document_type_definitions_global_code")
    op.drop_table("document_type_definitions")
