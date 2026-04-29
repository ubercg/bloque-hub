"""space_booking_rules table + MAINTENANCE enum value for SlotStatus.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
Create Date: 2026-03-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "w3x4y5z6a7b8"
down_revision: Union[str, None] = "v2w3x4y5z6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add MAINTENANCE to SlotStatus enum
    op.execute("ALTER TYPE slotstatus ADD VALUE IF NOT EXISTS 'MAINTENANCE'")

    # 2. Create space_booking_rules table
    op.create_table(
        "space_booking_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True), sa.ForeignKey("spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("min_duration_minutes", sa.Integer, nullable=False, server_default="60"),
        sa.Column("allowed_start_times", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("space_id", name="uq_space_booking_rules_space"),
    )

    # 3. RLS policies for tenant isolation
    op.execute("ALTER TABLE space_booking_rules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE space_booking_rules FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON space_booking_rules
        USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_insert ON space_booking_rules
        FOR INSERT WITH CHECK (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
    """)

    # 4. Grant permissions to bloque_app
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON space_booking_rules TO bloque_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_insert ON space_booking_rules")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON space_booking_rules")
    op.drop_table("space_booking_rules")
    # Note: PostgreSQL does not support removing enum values;
    # MAINTENANCE will remain in the enum after downgrade.
