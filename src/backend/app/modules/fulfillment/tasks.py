"""Tareas Celery para fulfillment (MONTAJE_NO_INICIADO, etc.)."""

from app.celery_app import app
from app.db.session import get_db_context
from app.modules.fulfillment.services import (
    MONTAJE_TOLERANCE_MINUTES,
    raise_montaje_no_iniciado_incidents,
)


@app.task(name="fulfillment.check_montaje_no_iniciado")
def check_montaje_no_iniciado(tolerance_minutes: int | None = None) -> int:
    """
    Revisa OS con montaje programado que no han iniciado en la ventana de tolerancia,
    crea incidencia MONTAJE_NO_INICIADO y devuelve cuántas se crearon.
    Programado en beat cada 10 min.
    """
    with get_db_context(tenant_id=None, role="SUPERADMIN") as db:
        n = raise_montaje_no_iniciado_incidents(
            db, tolerance_minutes or MONTAJE_TOLERANCE_MINUTES
        )
        db.commit()
        return n
