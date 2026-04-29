"""audit_log: append-only table for state change audit. REVOKE UPDATE/DELETE from app role.

Revision ID: v2w3x4y5z6a7
Revises: u1v2w3x4y5z6
Create Date: 2026-02-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "v2w3x4y5z6a7"
down_revision: Union[str, None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tabla", sa.String(100), nullable=False),
        sa.Column("registro_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("campo_modificado", sa.String(100), nullable=True),
        sa.Column("valor_anterior", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("valor_nuevo", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_ip", sa.String(45), nullable=True),
        sa.Column("actor_user_agent", sa.Text(), nullable=True),
        sa.Column("registrado_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("correlacion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_audit_tenant_tabla", "audit_log", ["tenant_id", "tabla", "registrado_at"])
    op.create_index("idx_audit_registro", "audit_log", ["registro_id", "registrado_at"])
    op.create_index("idx_audit_actor", "audit_log", ["actor_id", "registrado_at"])

    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM PUBLIC")
    op.execute("REVOKE UPDATE, DELETE ON audit_log FROM bloque_app")
    op.execute("GRANT SELECT, INSERT ON audit_log TO bloque_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE audit_log_id_seq TO bloque_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON audit_log FROM bloque_app")
    op.drop_index("idx_audit_actor", table_name="audit_log")
    op.drop_index("idx_audit_registro", table_name="audit_log")
    op.drop_index("idx_audit_tenant_tabla", table_name="audit_log")
    op.drop_table("audit_log")
