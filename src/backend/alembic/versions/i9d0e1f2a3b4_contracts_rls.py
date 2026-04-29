"""contracts table with RLS

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

contractstatus_enum = postgresql.ENUM(
    "pending",
    "sent",
    "signed",
    "rejected",
    "expired",
    name="contractstatus",
    create_type=False,
)

revision: str = "i9d0e1f2a3b4"
down_revision: Union[str, None] = "h8c9d0e1f2a3"
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
        "DO $$ BEGIN CREATE TYPE contractstatus AS ENUM ("
        "'pending', 'sent', 'signed', 'rejected', 'expired'"
        "); EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )

    op.create_table(
        "contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", contractstatus_enum, nullable=False),
        sa.Column("provider_document_id", sa.String(length=255), nullable=True),
        sa.Column("signed_document_url", sa.String(length=512), nullable=True),
        sa.Column("fea_provider", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delegate_signer_activated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", name="uq_contracts_quote_id"),
    )
    op.create_index(op.f("ix_contracts_tenant_id"), "contracts", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_contracts_quote_id"), "contracts", ["quote_id"], unique=True)
    op.create_index(op.f("ix_contracts_status"), "contracts", ["status"], unique=False)
    op.create_index(
        op.f("ix_contracts_provider_document_id"),
        "contracts",
        ["provider_document_id"],
        unique=False,
    )

    _rls("contracts")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON contracts")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON contracts")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON contracts")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON contracts")
    op.execute("ALTER TABLE contracts DISABLE ROW LEVEL SECURITY")

    op.drop_index(op.f("ix_contracts_provider_document_id"), table_name="contracts")
    op.drop_index(op.f("ix_contracts_status"), table_name="contracts")
    op.drop_index(op.f("ix_contracts_quote_id"), table_name="contracts")
    op.drop_index(op.f("ix_contracts_tenant_id"), table_name="contracts")
    op.drop_table("contracts")

    op.execute("DROP TYPE contractstatus")
