"""quotes.portal_folio + quote_wizard_details + quote_wizard_documents (REQ-012)

Revision ID: q1r2s3t4u5v6
Revises: i5j6k7l8m9n0
Create Date: 2026-07-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, None] = "i5j6k7l8m9n0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TIPO_EVENTO_VALUES = (
    "Firma de convenio",
    "Conferencia",
    "Taller / Workshop",
    "Presentación",
    "Networking",
    "Rueda de prensa",
    "Reunión institucional",
    "Otro",
)
CARACTER_EVENTO_VALUES = (
    "Público",
    "Privado",
    "Gubernamental",
    "Académico",
    "Empresarial",
)
SECTOR_VALUES = (
    "Gobierno municipal/estatal/federal",
    "Universidad / Institución educativa",
    "Empresa privada",
    "Organismo internacional",
    "Organización civil",
    "Startup / Emprendimiento",
    "Otro",
)
COMO_CONOCISTE_VALUES = (
    "Recomendación de otra institución",
    "Redes sociales",
    "Sitio web del Municipio",
    "Ya he realizado eventos anteriores",
    "Otro",
)
MONTAJE_REQUERIDO_VALUES = (
    "Estándar (mesas y sillas en U)",
    "Teatro",
    "Aula",
    "Cóctel",
    "Protocolar para firma",
    "Sin montaje",
)

tipo_evento_enum = postgresql.ENUM(
    *TIPO_EVENTO_VALUES, name="tipo_evento", create_type=False
)
caracter_evento_enum = postgresql.ENUM(
    *CARACTER_EVENTO_VALUES, name="caracter_evento", create_type=False
)
sector_enum = postgresql.ENUM(*SECTOR_VALUES, name="sector", create_type=False)
como_conociste_enum = postgresql.ENUM(
    *COMO_CONOCISTE_VALUES, name="como_conociste", create_type=False
)
montaje_requerido_enum = postgresql.ENUM(
    *MONTAJE_REQUERIDO_VALUES, name="montaje_requerido", create_type=False
)


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


def _drop_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}")
    op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
    op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _create_enum_type(name: str, values: tuple[str, ...]) -> None:
    values_sql = ", ".join(f"'{v}'" for v in values)
    op.execute(
        f"DO $$ BEGIN CREATE TYPE {name} AS ENUM ({values_sql}); "
        f"EXCEPTION WHEN duplicate_object THEN NULL; END $$"
    )


def upgrade() -> None:
    # 1. Quote.portal_folio (nullable; internal COMMERCIAL quotes leave it NULL)
    op.add_column("quotes", sa.Column("portal_folio", sa.String(length=32), nullable=True))
    op.create_index(
        op.f("ix_quotes_portal_folio"), "quotes", ["portal_folio"], unique=False
    )
    # Partial unique index: only non-null folios must be unique (RN-013 replay protection).
    op.execute(
        "CREATE UNIQUE INDEX uq_quotes_portal_folio ON quotes (portal_folio) "
        "WHERE portal_folio IS NOT NULL"
    )

    # 2. Enum types (REQ-012 §4 frozen values)
    _create_enum_type("tipo_evento", TIPO_EVENTO_VALUES)
    _create_enum_type("caracter_evento", CARACTER_EVENTO_VALUES)
    _create_enum_type("sector", SECTOR_VALUES)
    _create_enum_type("como_conociste", COMO_CONOCISTE_VALUES)
    _create_enum_type("montaje_requerido", MONTAJE_REQUERIDO_VALUES)

    # 3. quote_wizard_details (1:1 adjunct)
    op.create_table(
        "quote_wizard_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tipo_evento", tipo_evento_enum, nullable=False),
        sa.Column("nombre_evento", sa.String(length=255), nullable=True),
        sa.Column("caracter_evento", caracter_evento_enum, nullable=False),
        sa.Column("descripcion_evento", sa.Text(), nullable=True),
        sa.Column("asistentes_estimados", sa.Integer(), nullable=False),
        sa.Column("habra_prensa", sa.Boolean(), nullable=False),
        sa.Column("nombre_completo", sa.String(length=255), nullable=False),
        sa.Column("cargo_puesto", sa.String(length=255), nullable=True),
        sa.Column("institucion_organizacion", sa.String(length=255), nullable=True),
        sa.Column("sector", sector_enum, nullable=False),
        sa.Column("sector_otro", sa.String(length=255), nullable=True),
        sa.Column("correo_institucional", sa.String(length=255), nullable=False),
        sa.Column("telefono_contacto", sa.String(length=64), nullable=False),
        sa.Column("responsable_sitio_nombre", sa.String(length=255), nullable=True),
        sa.Column("responsable_sitio_telefono", sa.String(length=64), nullable=True),
        sa.Column("como_conociste_bloque", como_conociste_enum, nullable=False),
        sa.Column("como_conociste_otro", sa.String(length=255), nullable=True),
        sa.Column("montaje_requerido", montaje_requerido_enum, nullable=False),
        sa.Column("requerimientos_especiales", sa.Text(), nullable=True),
        sa.Column("material_externo", sa.Boolean(), nullable=False),
        sa.Column("material_externo_detalle", sa.Text(), nullable=True),
        sa.Column("acepta_info_correcta_autorizacion", sa.Boolean(), nullable=False),
        sa.Column("acepta_reglamento_y_aviso_privacidad", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_id", name="uq_quote_wizard_details_quote_id"),
    )
    op.create_index(
        op.f("ix_quote_wizard_details_tenant_id"),
        "quote_wizard_details",
        ["tenant_id"],
        unique=False,
    )
    _rls("quote_wizard_details")

    # 4. quote_wizard_documents (1:N)
    op.create_table(
        "quote_wizard_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quote_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_quote_wizard_documents_tenant_id"),
        "quote_wizard_documents",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_quote_wizard_documents_quote_id"),
        "quote_wizard_documents",
        ["quote_id"],
        unique=False,
    )
    _rls("quote_wizard_documents")


def downgrade() -> None:
    _drop_rls("quote_wizard_documents")
    op.drop_index(
        op.f("ix_quote_wizard_documents_quote_id"), table_name="quote_wizard_documents"
    )
    op.drop_index(
        op.f("ix_quote_wizard_documents_tenant_id"), table_name="quote_wizard_documents"
    )
    op.drop_table("quote_wizard_documents")

    _drop_rls("quote_wizard_details")
    op.drop_index(
        op.f("ix_quote_wizard_details_tenant_id"), table_name="quote_wizard_details"
    )
    op.drop_table("quote_wizard_details")

    op.execute("DROP TYPE montaje_requerido")
    op.execute("DROP TYPE como_conociste")
    op.execute("DROP TYPE sector")
    op.execute("DROP TYPE caracter_evento")
    op.execute("DROP TYPE tipo_evento")

    op.execute("DROP INDEX IF EXISTS uq_quotes_portal_folio")
    op.drop_index(op.f("ix_quotes_portal_folio"), table_name="quotes")
    op.drop_column("quotes", "portal_folio")
