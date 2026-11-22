from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "flowsentry",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "poll-enabled-integrations": {
            "task": "flowsentry.poll_enabled_integrations",
            "schedule": 120.0,
        },
        "evaluate-due-outcome-monitors": {
            "task": "flowsentry.evaluate_due_outcome_monitors",
            "schedule": 60.0,
        },
        "evaluate-frequency-anomalies": {
            "task": "flowsentry.evaluate_frequency_anomalies",
            "schedule": 180.0,
        },
    },
)


@celery_app.task(name="flowsentry.health_ping")
def health_ping() -> str:
    return "pong"
