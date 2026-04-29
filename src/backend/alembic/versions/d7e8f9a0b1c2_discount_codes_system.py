"""discount codes system

Revision ID: d7e8f9a0b1c2
Revises: 362d6bf6a8ba
Create Date: 2026-03-24 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "362d6bf6a8ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discount_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("discount_type", sa.String(length=16), nullable=False),
        sa.Column("discount_value", sa.Numeric(12, 4), nullable=False),
        sa.Column("min_subtotal", sa.Numeric(12, 4), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("single_use_per_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("discount_type IN ('PERCENT', 'FIXED')", name="ck_discount_codes_discount_type"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discount_codes_tenant_id", "discount_codes", ["tenant_id"], unique=False)
    op.execute(
        "CREATE UNIQUE INDEX uq_discount_codes_tenant_code_ci ON discount_codes (tenant_id, upper(code))"
    )

    op.create_table(
        "discount_code_usages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("discount_code_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("group_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("used_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("applied_subtotal", sa.Numeric(12, 4), nullable=False),
        sa.Column("applied_discount_amount", sa.Numeric(12, 4), nullable=False),
        sa.Column("applied_total", sa.Numeric(12, 4), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["discount_code_id"], ["discount_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discount_code_usages_tenant_id", "discount_code_usages", ["tenant_id"], unique=False)
    op.create_index("ix_discount_code_usages_discount_code_id", "discount_code_usages", ["discount_code_id"], unique=False)
    op.create_index("ix_discount_code_usages_group_event_id", "discount_code_usages", ["group_event_id"], unique=False)
    op.create_index("ix_discount_code_usages_reservation_id", "discount_code_usages", ["reservation_id"], unique=False)
    op.create_index("ix_discount_code_usages_used_by_user_id", "discount_code_usages", ["used_by_user_id"], unique=False)

    op.add_column("reservations", sa.Column("discount_code_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("reservations", sa.Column("discount_amount_applied", sa.Numeric(12, 2), nullable=True))
    op.create_index("ix_reservations_discount_code_id", "reservations", ["discount_code_id"], unique=False)
    op.create_foreign_key(
        "fk_reservations_discount_code_id",
        "reservations",
        "discount_codes",
        ["discount_code_id"],
        ["id"],
        ondelete="SET NULL",
    )

    for table in ("discount_codes", "discount_code_usages"):
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


def downgrade() -> None:
    for table in ("discount_code_usages", "discount_codes"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")

    op.drop_constraint("fk_reservations_discount_code_id", "reservations", type_="foreignkey")
    op.drop_index("ix_reservations_discount_code_id", table_name="reservations")
    op.drop_column("reservations", "discount_amount_applied")
    op.drop_column("reservations", "discount_code_id")

    op.drop_index("ix_discount_code_usages_used_by_user_id", table_name="discount_code_usages")
    op.drop_index("ix_discount_code_usages_reservation_id", table_name="discount_code_usages")
    op.drop_index("ix_discount_code_usages_group_event_id", table_name="discount_code_usages")
    op.drop_index("ix_discount_code_usages_discount_code_id", table_name="discount_code_usages")
    op.drop_index("ix_discount_code_usages_tenant_id", table_name="discount_code_usages")
    op.drop_table("discount_code_usages")

    op.drop_index("uq_discount_codes_tenant_code_ci", table_name="discount_codes")
    op.drop_index("ix_discount_codes_tenant_id", table_name="discount_codes")
    op.drop_table("discount_codes")
