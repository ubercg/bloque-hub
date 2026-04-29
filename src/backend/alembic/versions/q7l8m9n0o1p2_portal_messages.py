"""portal_messages table + RLS (T12.3)

Revision ID: q7l8m9n0o1p2
Revises: p6k7l8m9n0o1
Create Date: 2026-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "q7l8m9n0o1p2"
down_revision: Union[str, None] = "p6k7l8m9n0o1"
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


def upgrade() -> None:
    op.create_table(
        "portal_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reservations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("remitente_tipo", sa.String(32), nullable=False),
        sa.Column("remitente_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("enviado_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("leido_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_portal_messages_reservation_id", "portal_messages", ["reservation_id"], unique=False)
    op.create_index("ix_portal_messages_enviado_at", "portal_messages", ["enviado_at"], unique=False)
    op.create_index("ix_portal_messages_tenant_id", "portal_messages", ["tenant_id"], unique=False)
    _rls("portal_messages")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON portal_messages")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON portal_messages")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON portal_messages")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON portal_messages")
    op.drop_index("ix_portal_messages_tenant_id", table_name="portal_messages")
    op.drop_index("ix_portal_messages_enviado_at", table_name="portal_messages")
    op.drop_index("ix_portal_messages_reservation_id", table_name="portal_messages")
    op.drop_table("portal_messages")
