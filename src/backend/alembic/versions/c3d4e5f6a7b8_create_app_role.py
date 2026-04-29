"""create app role (non-superuser) for RLS to apply

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create role for application (non-superuser so RLS applies)
    op.execute(
        "DO $$ BEGIN "
        "CREATE ROLE bloque_app WITH LOGIN PASSWORD 'bloque_app_secret' NOSUPERUSER; "
        "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )
    op.execute("GRANT CONNECT ON DATABASE bloque_hub TO bloque_app")
    op.execute("GRANT USAGE ON SCHEMA public TO bloque_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bloque_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO bloque_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bloque_app"
    )


def downgrade() -> None:
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM bloque_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM bloque_app")
    op.execute("REVOKE CONNECT ON DATABASE bloque_hub FROM bloque_app")
    op.execute("DROP ROLE IF EXISTS bloque_app")
