"""Seed: COMPROBANTE_DOMICILIO en document_type_definitions (global).

Revision ID: g2h3i4j5k6l7
Revises: f1a2b3c4d5e6
"""

from typing import Sequence, Union

from alembic import op

revision: str = "g2h3i4j5k6l7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa6"
CODE = "COMPROBANTE_DOMICILIO"


def upgrade() -> None:
    # Deja hueco en sort_order 4 para el nuevo tipo (INE reverso queda en 3).
    op.execute(
        """
        UPDATE document_type_definitions
        SET sort_order = sort_order + 1
        WHERE tenant_id IS NULL AND sort_order >= 4
        """
    )
    op.execute("SELECT set_config('app.role', 'SUPERADMIN', true)")
    op.execute(
        f"""
        INSERT INTO document_type_definitions
            (id, tenant_id, code, label, required, requires_condition, mime_rules, active, sort_order)
        VALUES
            ('{NEW_ID}'::uuid, NULL, '{CODE}', 'Comprobante de domicilio', true, 'NONE',
             '["application/pdf","image/jpeg","image/png","image/jpg"]'::jsonb, true, 4)
        """
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM document_type_definitions WHERE id = '{NEW_ID}'::uuid AND code = '{CODE}'")
    op.execute(
        """
        UPDATE document_type_definitions
        SET sort_order = sort_order - 1
        WHERE tenant_id IS NULL AND sort_order >= 5
        """
    )
