"""RLS: permitir DELETE en reservation_documents (cleanup interno / SUPERADMIN).

Revision ID: f1a2b3c4d5e6
Revises: e3f4a5b6c7d8
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE POLICY tenant_isolation_delete ON reservation_documents
        FOR DELETE USING (
            tenant_id::text = current_setting('app.current_tenant_id', true)
            OR current_setting('app.role', true) = 'SUPERADMIN'
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation_delete ON reservation_documents")
