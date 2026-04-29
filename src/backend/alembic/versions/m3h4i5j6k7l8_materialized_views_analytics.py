"""Materialized views mv_dashboard_ejecutivo and mv_finanzas_kpis (FR-29 to FR-32)

Revision ID: m3h4i5j6k7l8
Revises: l2g3h4i5j6k7
Create Date: 2026-02-25

"""
from typing import Sequence, Union

from alembic import op

revision: str = "m3h4i5j6k7l8"
down_revision: Union[str, None] = "l2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE MATERIALIZED VIEW mv_dashboard_ejecutivo AS
        WITH res AS (
            SELECT
                tenant_id,
                date_trunc('month', fecha)::date AS year_month,
                COUNT(*) FILTER (WHERE status = 'CONFIRMED') AS reservations_confirmed
            FROM reservations
            GROUP BY tenant_id, date_trunc('month', fecha)::date
        ),
        quo AS (
            SELECT
                q.tenant_id,
                date_trunc('month', q.updated_at)::date AS year_month,
                COUNT(c.id) FILTER (WHERE c.status = 'signed') AS contracts_signed,
                COALESCE(SUM(q.total) FILTER (WHERE q.status = 'APPROVED'), 0) AS total_revenue
            FROM quotes q
            LEFT JOIN contracts c ON c.quote_id = q.id
            GROUP BY q.tenant_id, date_trunc('month', q.updated_at)::date
        )
        SELECT
            COALESCE(res.tenant_id, quo.tenant_id) AS tenant_id,
            COALESCE(res.year_month, quo.year_month) AS year_month,
            COALESCE(res.reservations_confirmed, 0)::bigint AS reservations_confirmed,
            COALESCE(quo.contracts_signed, 0)::bigint AS contracts_signed,
            COALESCE(quo.total_revenue, 0)::numeric(12,2) AS total_revenue_approved_quotes
        FROM res
        FULL OUTER JOIN quo ON res.tenant_id = quo.tenant_id AND res.year_month = quo.year_month
    """)
    op.execute("CREATE UNIQUE INDEX uq_mv_dashboard_tenant_month ON mv_dashboard_ejecutivo (tenant_id, year_month)")

    op.execute("""
        CREATE MATERIALIZED VIEW mv_finanzas_kpis AS
        WITH base AS (
            SELECT
                q.tenant_id,
                date_trunc('month', q.updated_at)::date AS year_month,
                COUNT(*) FILTER (WHERE q.status = 'APPROVED') AS quotes_approved_count,
                COALESCE(SUM(q.total) FILTER (WHERE q.status = 'APPROVED'), 0) AS quotes_total_amount,
                COUNT(c.id) FILTER (WHERE c.status = 'signed') AS contracts_signed_count
            FROM quotes q
            LEFT JOIN contracts c ON c.quote_id = q.id
            GROUP BY q.tenant_id, date_trunc('month', q.updated_at)::date
        )
        SELECT tenant_id, year_month, quotes_approved_count, quotes_total_amount, contracts_signed_count FROM base
    """)
    op.execute("CREATE UNIQUE INDEX uq_mv_finanzas_tenant_month ON mv_finanzas_kpis (tenant_id, year_month)")

    # So app role can REFRESH and SELECT (materialized views are not covered by ALL TABLES)
    op.execute("ALTER MATERIALIZED VIEW mv_dashboard_ejecutivo OWNER TO bloque_app")
    op.execute("ALTER MATERIALIZED VIEW mv_finanzas_kpis OWNER TO bloque_app")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_finanzas_kpis")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_ejecutivo")
