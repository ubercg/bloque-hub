"""payment_vouchers table with RLS (FR-11)

Revision ID: r8m9n0o1p2q3
Revises: q7l8m9n0o1p2
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "r8m9n0o1p2q3"
down_revision: Union[str, None] = "q7l8m9n0o1p2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rls(table: str) -> None:
    """Enable RLS with tenant isolation policy."""
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


def upgrade() -> None:
    # Create payment_vouchers table
    op.create_table(
        'payment_vouchers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reservation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_url', sa.String(length=500), nullable=False),
        sa.Column('file_type', sa.String(length=100), nullable=False),
        sa.Column('file_size_kb', sa.Integer(), nullable=False),
        sa.Column('sha256_hash', sa.String(length=64), nullable=False),
        sa.Column('uploaded_by_ip', sa.String(length=45), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['reservation_id'], ['reservations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sha256_hash', name='uq_payment_vouchers_sha256_hash')
    )

    # Create indexes
    op.create_index('ix_payment_vouchers_tenant_id', 'payment_vouchers', ['tenant_id'], unique=False)
    op.create_index('ix_payment_vouchers_reservation_id', 'payment_vouchers', ['reservation_id'], unique=False)

    # Enable RLS
    _rls('payment_vouchers')


def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON payment_vouchers")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON payment_vouchers")

    # Drop indexes
    op.drop_index('ix_payment_vouchers_reservation_id', table_name='payment_vouchers')
    op.drop_index('ix_payment_vouchers_tenant_id', table_name='payment_vouchers')

    # Drop table
    op.drop_table('payment_vouchers')
