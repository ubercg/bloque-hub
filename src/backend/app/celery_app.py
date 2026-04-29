"""Celery application for background and periodic tasks."""

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

app = Celery(
    "bloque_hub",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.modules.booking.tasks",
        "app.modules.crm.tasks",
        "app.modules.analytics.tasks",
        "app.modules.notifications.tasks",
    ],
)
app.conf.timezone = "UTC"
app.conf.task_serializer = "json"
app.conf.result_serializer = "json"
app.conf.accept_content = ["json"]

app.conf.beat_schedule = {
    "expire-reservations-ttl": {
        "task": "booking.expire_reservations_ttl",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    "crm-add-delegate-signer": {
        "task": "crm.add_delegate_signer",
        "schedule": crontab(minute="*/20"),  # every 20 minutes
    },
    "analytics-refresh-materialized-views": {
        "task": "analytics.refresh_materialized_views",
        "schedule": crontab(minute="*/5"),  # every 5 minutes
    },
    "notifications-send-ttl-reminders": {
        "task": "notifications.send_ttl_reminders",
        "schedule": crontab(minute="*/10"),  # every 10 minutes (recordatorio ~4h antes)
    },
    "complete-past-events": {
        "task": "booking.complete_past_events",
        "schedule": crontab(minute="*/15"),  # every 15 minutes
    },
    "cleanup-orphan-kyc-drafts": {
        "task": "booking.cleanup_orphan_kyc_drafts",
        "schedule": crontab(hour=3, minute=12),  # daily UTC — borradores huérfanos
    },
}
