"""Tests for analytics materialized views (T10.2): existence, refresh, query performance."""

import time

import pytest
from sqlalchemy import text

from app.db.session import engine
from app.modules.analytics.tasks import refresh_materialized_views


def test_mv_dashboard_ejecutivo_exists_and_queryable() -> None:
    """mv_dashboard_ejecutivo exists and can be queried."""
    with engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM mv_dashboard_ejecutivo"))
        count = r.scalar()
    assert count is not None
    assert count >= 0


def test_mv_finanzas_kpis_exists_and_queryable() -> None:
    """mv_finanzas_kpis exists and can be queried."""
    with engine.connect() as conn:
        r = conn.execute(text("SELECT COUNT(*) FROM mv_finanzas_kpis"))
        count = r.scalar()
    assert count is not None
    assert count >= 0


def test_refresh_materialized_views_task_runs() -> None:
    """refresh_materialized_views task runs without error."""
    refresh_materialized_views()


def test_materialized_view_query_under_200ms() -> None:
    """Queries to materialized views respond in < 200ms (benchmark)."""
    with engine.connect() as conn:
        t0 = time.perf_counter()
        conn.execute(text("SELECT * FROM mv_dashboard_ejecutivo LIMIT 10"))
        elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 200, f"mv_dashboard_ejecutivo query took {elapsed_ms:.1f}ms (expected < 200ms)"
