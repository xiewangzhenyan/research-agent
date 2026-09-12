"""Celery application configuration."""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "agent",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
)

celery_app.autodiscover_tasks(["app.worker.tasks"])

celery_app.conf.imports = ("app.worker.tasks.knowledge",)
celery_app.conf.beat_schedule = {
    "dispatch-knowledge": {"task": "knowledge.dispatch", "schedule": 30.0}
}
