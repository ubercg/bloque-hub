"""Celery tasks for analytics: refresh materialized views."""

from sqlalchemy import text

from app.celery_app import app
from app.db.session import engine


@app.task(name="analytics.refresh_materialized_views")
def refresh_materialized_views() -> None:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY for dashboard views (every 5 min)."""
    with engine.connect() as conn:
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_dashboard_ejecutivo"))
        conn.commit()
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_finanzas_kpis"))
        conn.commit()
