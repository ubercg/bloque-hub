"""expediente_documents: Chain of Trust (NOM-151) append-only + RLS

Revision ID: l2g3h4i5j6k7
Revises: k1f2a3b4c5d6
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "l2g3h4i5j6k7"
down_revision: Union[str, None] = "k1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls_select_insert_only(table: str) -> None:
    """Append-only: only SELECT and INSERT policies; no UPDATE/DELETE."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
        FOR SELECT
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
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def upgrade() -> None:
    op.create_table(
        "expediente_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("document_url", sa.Text(), nullable=True),
        sa.Column("doc_sha256", sa.String(length=64), nullable=False),
        sa.Column("chain_prev_sha256", sa.String(length=64), nullable=True),
        sa.Column("chain_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "reservation_id IS NOT NULL OR contract_id IS NOT NULL",
            name="chk_expediente_reservation_or_contract",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["reservations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contracts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_expediente_documents_tenant_id"),
        "expediente_documents",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expediente_documents_reservation_id"),
        "expediente_documents",
        ["reservation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expediente_documents_contract_id"),
        "expediente_documents",
        ["contract_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_expediente_documents_created_at"),
        "expediente_documents",
        ["created_at"],
        unique=False,
    )

    _rls_select_insert_only("expediente_documents")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON expediente_documents")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON expediente_documents")
    op.execute("ALTER TABLE expediente_documents DISABLE ROW LEVEL SECURITY")

    op.drop_index(
        op.f("ix_expediente_documents_created_at"),
        table_name="expediente_documents",
    )
    op.drop_index(
        op.f("ix_expediente_documents_contract_id"),
        table_name="expediente_documents",
    )
    op.drop_index(
        op.f("ix_expediente_documents_reservation_id"),
        table_name="expediente_documents",
    )
    op.drop_index(
        op.f("ix_expediente_documents_tenant_id"),
        table_name="expediente_documents",
    )
    op.drop_table("expediente_documents")
