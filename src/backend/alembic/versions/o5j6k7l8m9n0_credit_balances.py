"""credit_balances table + RLS (T10.5)

Revision ID: o5j6k7l8m9n0
Revises: n4i5j6k7l8m9
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "o5j6k7l8m9n0"
down_revision: Union[str, None] = "n4i5j6k7l8m9"
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
        "credit_balances",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cfdi_uuid", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("monto_original", sa.Numeric(12, 2), nullable=False),
        sa.Column("saldo_restante", sa.Numeric(12, 2), nullable=False),
        sa.Column("reservation_origen_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("aplicado_a_reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_origen_id"], ["reservations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["aplicado_a_reservation_id"], ["reservations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_balances_tenant_id", "credit_balances", ["tenant_id"], unique=False)
    op.create_index("ix_credit_balances_cfdi_uuid", "credit_balances", ["cfdi_uuid"], unique=False)
    _rls("credit_balances")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON credit_balances")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_update ON credit_balances")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON credit_balances")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON credit_balances")
    op.execute("ALTER TABLE credit_balances DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_credit_balances_cfdi_uuid", table_name="credit_balances")
    op.drop_index("ix_credit_balances_tenant_id", table_name="credit_balances")
    op.drop_table("credit_balances")
