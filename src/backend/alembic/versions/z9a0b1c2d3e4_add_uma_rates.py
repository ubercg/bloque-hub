"""Add uma rates

Revision ID: z9a0b1c2d3e4
Revises: y5z6a7b8c9d0
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'z9a0b1c2d3e4'
down_revision: Union[str, None] = 'y5z6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'uma_rates',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_uma_rates_tenant_id'), 'uma_rates', ['tenant_id'], unique=False)
    
    # RLS Policy setup
    op.execute("ALTER TABLE uma_rates ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_uma_rates ON uma_rates "
        "USING (tenant_id = current_setting('app.current_tenant')::uuid)"
    )

def downgrade() -> None:
    op.execute("DROP POLICY tenant_isolation_uma_rates ON uma_rates")
    op.drop_index(op.f('ix_uma_rates_tenant_id'), table_name='uma_rates')
    op.drop_table('uma_rates')
